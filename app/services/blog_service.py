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
from typing import Optional

from app.config.settings import Settings
from app.core.exceptions import InsufficientArticlesError
from app.core.logging import get_logger
from app.models.blog import BlogResponse
from app.providers.github_client import GitHubClient
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
        github_client: Optional[GitHubClient] = None,
    ) -> None:
        self._news = news_service
        self._dedup = dedup_service
        self._llm = llm_service
        self._settings = settings
        self._github = github_client
        self._response_cache: dict[str, tuple[float, BlogResponse]] = {}

    async def generate(
        self,
        category: str = "general",
        country: str = "us",
        limit: int = 5,
        full_html: bool = True,
        q: str | None = None,
        github: bool = False,
    ) -> BlogResponse:
        cache_key = f"{'gh' if github else 'news'}:{category}:{country}:{limit}:{full_html}:{q or ''}"

        if self._settings.cache_enabled:
            cached = self._response_cache.get(cache_key)
            if cached and (time.monotonic() - cached[0]) < self._settings.cache_ttl_seconds:
                logger.info("Returning cached blog response", cache_key=cache_key)
                return cached[1]

        t_start = time.monotonic()
        logger.info(
            "Starting blog generation pipeline",
            source="github" if github else "newsapi",
            category=category,
            country=country,
            limit=limit,
            full_html=full_html,
            q=q,
        )

        if github:
            article_html, meta, sources, articles_used = await self._generate_from_github(q, limit)
        else:
            article_html, meta, sources, articles_used = await self._generate_from_news(
                category, country, limit, q
            )

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
            articles_used=articles_used,
            category=category,
            country=country,
            q=q,
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

    async def _generate_from_news(
        self,
        category: str,
        country: str,
        limit: int,
        q: str | None,
    ) -> tuple[str, dict, list[str], int]:
        articles = await self._news.fetch_articles(
            category=category,
            country=country,
            page_size=self._settings.max_news_fetch,
            q=q,
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

        return article_html, meta, [a.url for a in selected], len(selected)

    async def _generate_from_github(
        self,
        q: str | None,
        limit: int,
    ) -> tuple[str, dict, list[str], int]:
        if not self._github:
            raise InsufficientArticlesError(
                "GitHub source is not available.",
                detail={"hint": "Add GITHUB_TOKEN to your .env to enable GitHub trending"},
            )

        # Fetch a buffer so dedup has candidates to work with
        fetch_size = max(limit * 4, 20)
        repos = await self._github.fetch_trending_repos(q=q, page_size=fetch_size)

        if not repos:
            raise InsufficientArticlesError(
                "No trending GitHub repositories found. Try a different keyword or remove the q filter.",
                detail={"q": q},
            )

        new_repos = await self._dedup.filter_new_repos(repos, category="github")

        if not new_repos:
            raise InsufficientArticlesError(
                "All trending GitHub repositories have already been featured recently. Try again later or use a different keyword.",
                detail={"q": q, "fetched": len(repos)},
            )

        # Always write about the single most trending new repo
        repo = new_repos[0]
        logger.info("GitHub repo selected", repo=repo.full_name, stars=repo.stargazers_count)

        readme = await self._github.fetch_readme(repo.full_name)
        logger.info("README fetched", repo=repo.full_name, chars=len(readme) if readme else 0)

        image_url = (
            self._github.extract_image_from_readme(readme, full_name=repo.full_name)
            if readme else None
        ) or repo.owner.avatar_url

        logger.info("Image resolved", repo=repo.full_name, image_url=image_url)

        article_html, meta = await self._llm.generate_blog_from_repo(repo, readme=readme, image_url=image_url)
        await self._dedup.mark_repo_used(repo, category="github")

        return article_html, meta, [repo.html_url], 1
