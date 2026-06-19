from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config.settings import Settings
from app.core.exceptions import NewsAPIError, NewsAPIRateLimitError
from app.core.logging import get_logger
from app.models.news import NewsAPIResponse

logger = get_logger(__name__)

VALID_CATEGORIES = frozenset(
    {"business", "entertainment", "general", "health", "science", "sports", "technology"}
)


class NewsAPIClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.news_api_base_url,
            headers={"X-Api-Key": settings.news_api_key, "Accept": "application/json"},
            timeout=httpx.Timeout(settings.news_api_timeout),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type(NewsAPIError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def fetch_top_headlines(
        self,
        category: str = "general",
        country: str = "us",
        page_size: int = 20,
    ) -> NewsAPIResponse:
        safe_category = category if category in VALID_CATEGORIES else "general"

        params: dict[str, Any] = {
            "category": safe_category,
            "country": country,
            "pageSize": min(page_size, 100),
        }

        logger.info(
            "Fetching top headlines",
            category=safe_category,
            country=country,
            page_size=page_size,
        )

        try:
            response = await self._client.get("/top-headlines", params=params)
        except httpx.TimeoutException as exc:
            raise NewsAPIError("NewsAPI request timed out", detail=str(exc)) from exc
        except httpx.RequestError as exc:
            raise NewsAPIError("NewsAPI network error", detail=str(exc)) from exc

        if response.status_code == 429:
            raise NewsAPIRateLimitError("NewsAPI rate limit exceeded")

        if response.status_code == 401:
            raise NewsAPIError("NewsAPI authentication failed — check NEWS_API_KEY")

        if response.status_code != 200:
            raise NewsAPIError(
                f"NewsAPI returned HTTP {response.status_code}",
                detail=response.text[:500],
            )

        payload = response.json()

        if payload.get("status") != "ok":
            raise NewsAPIError(
                f"NewsAPI error: {payload.get('message', 'unknown')}",
                detail=payload,
            )

        parsed = NewsAPIResponse.model_validate(payload)

        logger.info(
            "Headlines fetched",
            total_results=parsed.total_results,
            returned=len(parsed.articles),
        )

        return parsed
