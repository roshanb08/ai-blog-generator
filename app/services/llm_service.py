import json
import re

from app.config.settings import Settings
from app.core.exceptions import LLMResponseParseError
from app.core.logging import get_logger
from app.models.news import NewsArticle
from app.providers.openrouter_client import OpenRouterClient
from app.providers.openwebui_client import OpenWebUIClient
from app.utils.html_utils import extract_html, validate_html_structure

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are an expert SEO journalist and blog writer. Produce a full blog article with SEO metadata.

OUTPUT FORMAT — two parts, nothing else, no markdown, no code fences:

PART 1 — A single compact JSON line (no line breaks inside it) with exactly these keys:
{"title":"SEO title 50-60 chars","meta_description":"Meta description 150-160 chars","keywords":"5-7 comma-separated keywords","og_title":"Open Graph title","og_description":"OG description max 200 chars"}

PART 2 — Starting on the very next line, the article HTML from <article> to </article>.

Article rules:
- Include a responsive <style> block inside <article> (no external CSS, no JS).
- Structure: <article> → <header> (h1) → one <section> per story (h2 + 2+ paragraphs) → <footer> with sources.
- If a story has a non-null image_url, put <img src="IMAGE_URL" alt="ARTICLE_TITLE" loading="lazy" style="width:100%;max-height:420px;object-fit:cover;border-radius:8px;margin-bottom:1rem;"> as the first element in its <section>.
- Do NOT invent or hallucinate image URLs — only use image_url values given in the JSON.
- Weave all stories into ONE cohesive narrative; do not repeat the same point across sections.
- Active voice, SEO-friendly headings, 600–1000 words total.\
"""

_USER_TEMPLATE = """\
Generate a blog article covering today's top {category} news.

News articles (JSON):
{articles_json}

Remember: output the compact JSON metadata on line 1, then the <article> HTML immediately after.\
"""


class LLMService:
    def __init__(self, client: OpenWebUIClient | OpenRouterClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def generate_blog(
        self,
        articles: list[NewsArticle],
        category: str = "general",
    ) -> tuple[str, dict[str, str]]:
        """
        Returns (article_html, meta) where meta has keys:
          title, meta_description, keywords, og_title, og_description
        """
        payload = self._build_article_payload(articles)
        user_message = _USER_TEMPLATE.format(
            category=category,
            articles_json=json.dumps(payload, ensure_ascii=False, indent=2),
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

        active_model = (
            self._settings.openrouter_model
            if self._settings.llm_provider == "openrouter"
            else self._settings.openwebui_model
        )

        logger.info(
            "Requesting blog generation",
            article_count=len(articles),
            category=category,
            model=active_model,
        )

        raw = await self._client.chat_completion(messages)

        logger.debug("LLM raw response", snippet=raw[:300])

        meta, html = _parse_response(raw)

        if not html:
            logger.error("No extractable HTML in LLM response", full_response=raw)
            raise LLMResponseParseError("LLM did not return valid HTML", detail=raw[:500])

        if not validate_html_structure(html):
            logger.warning("HTML structure incomplete — proceeding anyway")

        if not meta.get("title"):
            meta["title"] = _extract_h1(html) or f"Today's {category.capitalize()} News"

        logger.info(
            "Blog generated",
            title=meta.get("title", ""),
            html_length=len(html),
            meta_keys=list(meta.keys()),
        )

        return html, meta

    def _build_article_payload(self, articles: list[NewsArticle]) -> list[dict]:
        return [
            {
                "title": a.title,
                "author": a.author or "",
                "source": a.source.name,
                "published_at": a.published_at.isoformat(),
                "description": a.description or "",
                "content": (a.content or "")[:500],
                "image_url": a.url_to_image or None,
                "url": a.url,
            }
            for a in articles
        ]


# ── Response parsing ──────────────────────────────────────────────────────────

_JSON_LINE_RE = re.compile(r'^\s*(\{[^\n]+\})\s*$', re.MULTILINE)


def _parse_response(raw: str) -> tuple[dict[str, str], str]:
    """
    Extract (meta_dict, article_html) from the LLM response.

    The LLM is asked to output:
      Line 1: compact JSON
      Line 2+: <article>...</article>

    Gracefully falls back if the model doesn't follow format exactly.
    """
    meta: dict[str, str] = {}
    article_text = raw

    # Find the first JSON-looking line
    match = _JSON_LINE_RE.search(raw)
    if match:
        try:
            meta = json.loads(match.group(1))
            # Everything after the JSON line is the HTML
            after_json = raw[match.end():].strip()
            if after_json:
                article_text = after_json
        except (json.JSONDecodeError, ValueError):
            pass

    html = extract_html(article_text)
    return meta, html


def _extract_h1(html: str) -> str | None:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r"<[^>]+>", "", match.group(1)).strip() or None
    return None
