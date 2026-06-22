from app.config.settings import Settings
from app.core.logging import get_logger
from app.models.news import NewsArticle
from app.providers.newsapi_client import NewsAPIClient

logger = get_logger(__name__)


class NewsService:
    def __init__(self, client: NewsAPIClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def fetch_articles(
        self,
        category: str = "general",
        country: str = "us",
        page_size: int | None = None,
        q: str | None = None,
    ) -> list[NewsArticle]:
        fetch_size = page_size or self._settings.max_news_fetch

        logger.info(
            "Fetching articles",
            category=category,
            country=country,
            fetch_size=fetch_size,
            q=q,
        )

        response = await self._client.fetch_top_headlines(
            category=category,
            country=country,
            page_size=fetch_size,
            q=q,
        )

        articles = self._normalise(response.articles)

        logger.info(
            "Articles normalised",
            total=len(articles),
            category=category,
        )

        return articles

    def _normalise(self, articles: list[NewsArticle]) -> list[NewsArticle]:
        seen_urls: set[str] = set()
        result: list[NewsArticle] = []

        for article in articles:
            if not article.title or not article.url:
                continue
            if article.url in seen_urls:
                continue
            if not article.description and not article.content:
                continue
            seen_urls.add(article.url)
            result.append(article)

        return result
