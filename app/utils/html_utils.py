"""
HTML extraction, transformation, and full-document assembly.
"""

import json
import re
from datetime import datetime, timezone
from typing import Optional

_ARTICLE_RE = re.compile(r"(<article[\s\S]*?</article>)", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```(?:html)?\s*([\s\S]*?)```", re.IGNORECASE)
_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>[\s\S]*?</style>", re.IGNORECASE)
_IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_HEADER_RE = re.compile(r"<header[^>]*>([\s\S]*?)</header>", re.IGNORECASE)

_REQUIRED_TAGS = ["<article", "<header", "<h1", "<h2", "<section", "<p"]


# ── Extraction ────────────────────────────────────────────────────────────────

def extract_html(text: str) -> str:
    """
    Extract the <article> block from arbitrary LLM output.
    Handles bare HTML, markdown code fences, and prose wrappers.
    """
    stripped = text.strip()

    if stripped.lower().startswith("<article"):
        return stripped

    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        if candidate.lower().startswith("<article"):
            return candidate
        m = _ARTICLE_RE.search(candidate)
        if m:
            return m.group(1).strip()

    m = _ARTICLE_RE.search(text)
    if m:
        return m.group(1).strip()

    return ""


def validate_html_structure(html: str) -> bool:
    lower = html.lower()
    return all(tag in lower for tag in _REQUIRED_TAGS)


def extract_meta_description(html: str) -> Optional[str]:
    header = _HEADER_RE.search(html)
    if not header:
        return None
    p = _P_RE.search(header.group(1))
    if not p:
        return None
    raw = re.sub(r"<[^>]+>", "", p.group(1)).strip()
    return raw[:200] or None


def extract_first_image(html: str) -> Optional[str]:
    """Return the first non-data-URI image src in the HTML, or None."""
    for src in _IMG_SRC_RE.findall(html):
        if src.startswith("http"):
            return src
    return None


# ── Transformation ────────────────────────────────────────────────────────────

def strip_style_block(html: str) -> str:
    """Remove all <style>...</style> blocks from the HTML."""
    return _STYLE_BLOCK_RE.sub("", html).strip()


# ── Full document assembly ────────────────────────────────────────────────────

def build_full_document(
    article_html: str,
    meta: dict[str, str],
    sources: list[str],
    category: str = "general",
) -> str:
    """
    Wrap article_html in a complete <!DOCTYPE html> document with:
      - Primary SEO meta tags
      - Open Graph tags
      - Twitter Card tags
      - Schema.org NewsArticle JSON-LD
    """
    title = _esc(meta.get("title", "News Blog"))
    meta_description = _esc(meta.get("meta_description", ""))
    keywords = _esc(meta.get("keywords", ""))
    og_title = _esc(meta.get("og_title") or meta.get("title", ""))
    og_description = _esc(meta.get("og_description") or meta.get("meta_description", ""))
    og_image = extract_first_image(article_html) or ""

    published = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    og_image_tags = ""
    if og_image:
        og_image_tags = (
            f'  <meta property="og:image" content="{_esc(og_image)}">\n'
            f'  <meta name="twitter:image" content="{_esc(og_image)}">\n'
        )

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": meta.get("title", ""),
        "description": meta.get("meta_description", ""),
        "keywords": meta.get("keywords", ""),
        "datePublished": published,
        "author": {"@type": "Organization", "name": "AI Blog Generator"},
        "publisher": {
            "@type": "Organization",
            "name": "AI Blog Generator",
            "logo": {"@type": "ImageObject", "url": ""},
        },
        **({"image": [og_image]} if og_image else {}),
    }, ensure_ascii=False, indent=2)

    sources_html = "\n    ".join(
        f'<a href="{_esc(s)}" rel="noopener noreferrer" target="_blank">{_esc(s[:60])}</a>'
        for s in sources
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">

  <!-- Primary SEO -->
  <title>{title}</title>
  <meta name="description" content="{meta_description}">
  <meta name="keywords" content="{keywords}">
  <meta name="robots" content="index, follow">
  <meta name="author" content="AI Blog Generator">

  <!-- Open Graph -->
  <meta property="og:type" content="article">
  <meta property="og:title" content="{og_title}">
  <meta property="og:description" content="{og_description}">
  <meta property="og:locale" content="en_US">
{og_image_tags}
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{og_title}">
  <meta name="twitter:description" content="{og_description}">

  <!-- Schema.org JSON-LD -->
  <script type="application/ld+json">
{schema}
  </script>

  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
      background: #f5f5f5;
      color: #1a1a1a;
      line-height: 1.7;
    }}
  </style>
</head>
<body>
{article_html}
</body>
</html>"""


def _esc(text: str) -> str:
    """Escape characters that would break HTML attribute values."""
    return (
        text.replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
