"""
Deduplication engine backed by SQLite.

Strategy (layered — cheapest check first):
  1. Exact URL hash match
  2. Exact normalised-title hash match
  3. Jaccard similarity on word sets (catches minor rephrasing)

All seen articles are persisted with a configurable TTL so the service
survives restarts without re-surfacing old stories.
"""

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from app.config.settings import Settings
from app.core.exceptions import DeduplicationError
from app.core.logging import get_logger
from app.models.github_repo import GitHubRepo
from app.models.news import NewsArticle

logger = get_logger(__name__)

_STOP_WORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "is", "it", "its", "by", "as", "be", "was", "are",
        "from", "that", "this", "which", "have", "has", "had", "not", "no",
        "new", "says", "say", "said",
    }
)

_DDL = """
CREATE TABLE IF NOT EXISTS seen_articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash      TEXT NOT NULL UNIQUE,
    title_hash    TEXT NOT NULL,
    title_tokens  TEXT NOT NULL,
    published_at  TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_title_hash   ON seen_articles(title_hash);
CREATE INDEX IF NOT EXISTS idx_created_at   ON seen_articles(created_at);
"""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _normalise_title(title: str) -> str:
    lower = unicodedata.normalize("NFKD", title).lower()
    return re.sub(r"[^a-z0-9\s]", "", lower).strip()


def _tokenise(title: str) -> frozenset[str]:
    return frozenset(w for w in _normalise_title(title).split() if w not in _STOP_WORDS and len(w) > 1)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class DeduplicationService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db_path = settings.dedup_db_path
        self._threshold = settings.dedup_title_similarity_threshold
        self._ttl_hours = settings.dedup_ttl_hours
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_DDL)
        await self._db.commit()
        logger.info("DeduplicationService initialised", db_path=self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def filter_new(
        self, articles: list[NewsArticle], category: str = ""
    ) -> list[NewsArticle]:
        if not self._db:
            raise DeduplicationError("DeduplicationService not initialised — call init() first")

        await self._purge_expired()

        new_articles: list[NewsArticle] = []
        for article in articles:
            if await self._is_duplicate(article):
                logger.debug("Duplicate skipped", title=article.title[:80])
                continue
            new_articles.append(article)

        logger.info(
            "Deduplication complete",
            total_in=len(articles),
            total_out=len(new_articles),
            duplicates_removed=len(articles) - len(new_articles),
        )
        return new_articles

    async def mark_used(self, articles: list[NewsArticle], category: str = "") -> None:
        if not self._db:
            raise DeduplicationError("DeduplicationService not initialised")

        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (
                _sha256(article.url),
                _sha256(_normalise_title(article.title)),
                " ".join(sorted(_tokenise(article.title))),
                article.published_at.isoformat(),
                category,
                now,
            )
            for article in articles
        ]
        await self._db.executemany(
            """INSERT OR IGNORE INTO seen_articles
               (url_hash, title_hash, title_tokens, published_at, category, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await self._db.commit()
        logger.info("Marked articles as used", count=len(rows), category=category)

    async def filter_new_repos(
        self, repos: list[GitHubRepo], category: str = "github"
    ) -> list[GitHubRepo]:
        if not self._db:
            raise DeduplicationError("DeduplicationService not initialised — call init() first")

        new_repos: list[GitHubRepo] = []
        for repo in repos:
            if await self._is_repo_duplicate(repo):
                logger.debug("Duplicate repo skipped", repo=repo.full_name)
                continue
            new_repos.append(repo)

        logger.info(
            "GitHub repo deduplication complete",
            total_in=len(repos),
            total_out=len(new_repos),
        )
        return new_repos

    async def mark_repo_used(self, repo: GitHubRepo, category: str = "github") -> None:
        if not self._db:
            raise DeduplicationError("DeduplicationService not initialised")

        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT OR IGNORE INTO seen_articles
               (url_hash, title_hash, title_tokens, published_at, category, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                _sha256(repo.html_url),
                _sha256(_normalise_title(repo.full_name)),
                " ".join(sorted(_tokenise(repo.full_name))),
                repo.created_at,
                category,
                now,
            ),
        )
        await self._db.commit()
        logger.info("Marked GitHub repo as used", repo=repo.full_name)

    async def _is_repo_duplicate(self, repo: GitHubRepo) -> bool:
        assert self._db is not None

        url_hash = _sha256(repo.html_url)
        cursor = await self._db.execute(
            "SELECT 1 FROM seen_articles WHERE url_hash = ? LIMIT 1", (url_hash,)
        )
        if await cursor.fetchone():
            return True

        norm_title = _normalise_title(repo.full_name)
        title_hash = _sha256(norm_title)
        cursor = await self._db.execute(
            "SELECT 1 FROM seen_articles WHERE title_hash = ? LIMIT 1", (title_hash,)
        )
        if await cursor.fetchone():
            return True

        return False

    async def _is_duplicate(self, article: NewsArticle) -> bool:
        assert self._db is not None

        url_hash = _sha256(article.url)
        cursor = await self._db.execute(
            "SELECT 1 FROM seen_articles WHERE url_hash = ? LIMIT 1", (url_hash,)
        )
        if await cursor.fetchone():
            return True

        norm_title = _normalise_title(article.title)
        title_hash = _sha256(norm_title)
        cursor = await self._db.execute(
            "SELECT 1 FROM seen_articles WHERE title_hash = ? LIMIT 1", (title_hash,)
        )
        if await cursor.fetchone():
            return True

        candidate_tokens = _tokenise(article.title)
        if not candidate_tokens:
            return False

        cursor = await self._db.execute("SELECT title_tokens FROM seen_articles")
        async for row in cursor:
            stored_tokens = frozenset(row["title_tokens"].split())
            if _jaccard(candidate_tokens, stored_tokens) >= self._threshold:
                return True

        return False

    async def _purge_expired(self) -> None:
        assert self._db is not None

        from datetime import timedelta
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=self._ttl_hours)
        ).isoformat()

        result = await self._db.execute(
            "DELETE FROM seen_articles WHERE created_at < ?", (cutoff,)
        )
        await self._db.commit()
        if result.rowcount:
            logger.info("Expired dedup entries purged", count=result.rowcount)
