from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config.settings import Settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """
    OpenRouter drop-in: same chat_completion / close interface as OpenWebUIClient.
    OpenRouter is OpenAI-compatible, but recommends two extra headers
    (HTTP-Referer, X-Title) for model routing and attribution.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if settings.openrouter_site_url:
            headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_site_name:
            headers["X-Title"] = settings.openrouter_site_name

        self._client = httpx.AsyncClient(
            base_url=settings.openrouter_base_url,
            headers=headers,
            timeout=httpx.Timeout(settings.llm_timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception(lambda e: isinstance(e, LLMError) and not isinstance(e.__cause__, httpx.TimeoutException)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        reraise=True,
    )
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        settings = self._settings
        payload: dict[str, Any] = {
            "model": settings.openrouter_model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.llm_temperature,
            "max_tokens": max_tokens if max_tokens is not None else settings.llm_max_tokens,
            "stream": False,
        }

        logger.info(
            "Sending chat completion request via OpenRouter",
            model=settings.openrouter_model,
            message_count=len(messages),
        )

        try:
            response = await self._client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMError("OpenRouter request timed out", detail=str(exc)) from exc
        except httpx.RequestError as exc:
            raise LLMError("OpenRouter network error", detail=str(exc)) from exc

        if response.status_code == 401:
            raise LLMError("OpenRouter authentication failed — check OPENROUTER_API_KEY")

        if response.status_code == 429:
            raise LLMError("OpenRouter rate limit exceeded")

        if response.status_code != 200:
            raise LLMError(
                f"OpenRouter returned HTTP {response.status_code}",
                detail=response.text[:500],
            )

        data = response.json()

        # OpenRouter may surface provider errors inside a 200 body
        if error := data.get("error"):
            raise LLMError(
                f"OpenRouter provider error: {error.get('message', 'unknown')}",
                detail=error,
            )

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError("Unexpected OpenRouter response structure", detail=data) from exc

        if content is None:
            finish_reason = data.get("choices", [{}])[0].get("finish_reason", "unknown")
            raise LLMError(
                f"OpenRouter returned null content (finish_reason={finish_reason!r}). "
                "The model may have refused the request or hit a context limit.",
                detail=data,
            )

        logger.info(
            "OpenRouter chat completion received",
            response_length=len(content),
            finish_reason=data.get("choices", [{}])[0].get("finish_reason"),
        )
        logger.debug("OpenRouter raw response", raw=content)

        return content
