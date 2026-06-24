import base64
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config.settings import Settings
from app.core.exceptions import GitHubAPIError
from app.core.logging import get_logger
from app.models.github_repo import GitHubRepo, GitHubSearchResponse

logger = get_logger(__name__)


class GitHubClient:
    _BASE_URL = "https://api.github.com"

    def __init__(self, settings: Settings) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"

        self._client = httpx.AsyncClient(
            base_url=self._BASE_URL,
            headers=headers,
            timeout=httpx.Timeout(15),
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type(GitHubAPIError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def fetch_trending_repos(
        self,
        q: Optional[str] = None,
        since_days: int = 7,
        page_size: int = 10,
    ) -> list[GitHubRepo]:
        since_date = (
            datetime.now(timezone.utc) - timedelta(days=since_days)
        ).strftime("%Y-%m-%d")

        query_parts = [f"created:>{since_date}", "stars:>5"]
        if q:
            query_parts.append(q)

        params = {
            "q": " ".join(query_parts),
            "sort": "stars",
            "order": "desc",
            "per_page": min(page_size, 30),
        }

        logger.info("Fetching trending GitHub repos", query=params["q"], page_size=page_size)

        try:
            response = await self._client.get("/search/repositories", params=params)
        except httpx.TimeoutException as exc:
            raise GitHubAPIError("GitHub API timed out", detail=str(exc)) from exc
        except httpx.RequestError as exc:
            raise GitHubAPIError("GitHub API network error", detail=str(exc)) from exc

        if response.status_code == 403:
            raise GitHubAPIError(
                "GitHub API rate limit exceeded — set GITHUB_TOKEN for higher limits",
                detail=response.text[:200],
            )

        if response.status_code != 200:
            raise GitHubAPIError(
                f"GitHub API returned HTTP {response.status_code}",
                detail=response.text[:200],
            )

        parsed = GitHubSearchResponse.model_validate(response.json())

        logger.info(
            "GitHub repos fetched",
            total=parsed.total_count,
            returned=len(parsed.items),
        )

        return parsed.items

    async def fetch_readme(self, full_name: str, max_chars: int = 3000) -> Optional[str]:
        """Fetch and decode the README for a repo. Returns None if unavailable."""
        try:
            response = await self._client.get(f"/repos/{full_name}/readme")
        except (httpx.TimeoutException, httpx.RequestError):
            return None

        if response.status_code != 200:
            return None

        try:
            data = response.json()
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return content[:max_chars]
        except Exception:
            return None
