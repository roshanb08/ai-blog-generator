"""
BlogService — the main pipeline orchestrator.

Pipeline:
  1. Fetch raw articles from NewsAPI
  2. Filter duplicates via DeduplicationService
  3. Select the top N stories
  4. Generate cohesive HTML + SEO metadata via LLMService
  5. Assemble full HTML doc or bare article depending on full_html flag
  6. Mark used articles in dedup store
  7. Return structured BlogResponse
"""

import time

from app.config.settings import Settings
from app.core.exceptions import InsufficientArticlesError
from app.core.logging import get_logger
from app.models.blog import BlogResponse
from app.services.dedup_service import DeduplicationService
from app.services.llm_service import LLMService
from app.services.news_service import NewsService
from app.utils.html_utils import (
    build_full_document,
    extract_first_image,
    strip_style_block,
)

logger = get_logger(__name__)

_MIN_ARTICLES = 2


class BlogService:
    def __init__(
        self,
        news_service: NewsService,
        dedup_service: DeduplicationService,
        llm_service: LLMService,
        settings: Settings,
    ) -> None:
        self._news = news_service
        self._dedup = dedup_service
        self._llm = llm_service
        self._settings = settings
        self._response_cache: dict[str, tuple[float, BlogResponse]] = {}

    async def generate(
        self,
        category: str = "general",
        country: str = "us",
        limit: int = 5,
        full_html: bool = True,
    ) -> BlogResponse:
        cache_key = f"{category}:{country}:{limit}:{full_html}"

        if self._settings.cache_enabled:
            cached = self._response_cache.get(cache_key)
            if cached and (time.monotonic() - cached[0]) < self._settings.cache_ttl_seconds:
                logger.info("Returning cached blog response", cache_key=cache_key)
                return cached[1]

        t_start = time.monotonic()
        logger.info(
            "Starting blog generation pipeline",
            category=category,
            country=country,
            limit=limit,
            full_html=full_html,
        )

        articles = await self._news.fetch_articles(
            category=category,
            country=country,
            page_size=self._settings.max_news_fetch,
        )

        unique_articles = await self._dedup.filter_new(articles, category=category)

        if len(unique_articles) < _MIN_ARTICLES:
            raise InsufficientArticlesError(
                f"Only {len(unique_articles)} unique article(s) found after deduplication "
                f"(minimum {_MIN_ARTICLES} required). Try a different category or wait for new stories.",
                detail={
                    "fetched": len(articles),
                    "unique": len(unique_articles),
                    "category": category,
                    "country": country,
                },
            )

        selected = unique_articles[:limit]
        logger.info("Articles selected", selected=len(selected), available=len(unique_articles))

        article_html, meta = await self._llm.generate_blog(selected, category=category)

        await self._dedup.mark_used(selected, category=category)

        sources = [a.url for a in selected]
        og_image = extract_first_image(article_html)

        if full_html:
            final_html = build_full_document(article_html, meta, sources, category)
        else:
            final_html = strip_style_block(article_html)

        response = BlogResponse(
            title=meta.get("title", f"Today's {category.capitalize()} News"),
            html=final_html,
            full_html=full_html,
            meta_description=meta.get("meta_description"),
            keywords=meta.get("keywords"),
            og_title=meta.get("og_title") or meta.get("title"),
            og_description=meta.get("og_description") or meta.get("meta_description"),
            og_image=og_image,
            sources=sources,
            articles_used=len(selected),
            category=category,
            country=country,
        )

        if self._settings.cache_enabled:
            self._response_cache[cache_key] = (time.monotonic(), response)

        elapsed = time.monotonic() - t_start
        logger.info(
            "Blog generation complete",
            elapsed_seconds=round(elapsed, 2),
            title=response.title,
            full_html=full_html,
        )

        return response
