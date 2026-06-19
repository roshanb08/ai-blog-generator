"""
Post-process generated HTML to embed external images as base64 data URIs.

Strategy:
  - Extract every unique https:// src from <img> tags in the HTML.
  - Fetch them all concurrently with a short timeout.
  - Replace each successfully-fetched URL with a data URI.
  - Leave failed / oversized / non-image URLs untouched (external URL remains).

This runs AFTER the LLM generates HTML, so no base64 ever enters the prompt.
"""

import asyncio
import base64
import re

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

_IMG_SRC_RE = re.compile(r'src="(https?://[^"]+)"', re.IGNORECASE)

_MAX_IMAGE_BYTES = 512_000   # 500 KB raw → ~667 KB base64; skip anything larger
_FETCH_TIMEOUT = 8.0


async def embed_images_as_base64(html: str) -> str:
    """
    Replace all external image src URLs in *html* with inline base64 data URIs.
    Returns the modified HTML (or the original if no images are found / all fail).
    """
    urls = list(dict.fromkeys(_IMG_SRC_RE.findall(html)))  # unique, order-preserving
    if not urls:
        return html

    logger.info("Embedding images as base64", count=len(urls))

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_FETCH_TIMEOUT),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10),
    ) as client:
        results = await asyncio.gather(
            *[_fetch_as_data_url(url, client) for url in urls],
            return_exceptions=True,
        )

    url_map: dict[str, str] = {}
    for url, result in zip(urls, results):
        if isinstance(result, str):
            url_map[url] = result
            logger.debug("Image embedded", url=url[:80], data_uri_len=len(result))
        else:
            logger.debug("Image skipped", url=url[:80], reason=str(result)[:120])

    if not url_map:
        logger.warning("No images could be embedded; returning HTML with original URLs")
        return html

    def replace_src(match: re.Match) -> str:
        url = match.group(1)
        return f'src="{url_map.get(url, url)}"'

    embedded = _IMG_SRC_RE.sub(replace_src, html)
    logger.info("Image embedding complete", embedded=len(url_map), skipped=len(urls) - len(url_map))
    return embedded


async def _fetch_as_data_url(url: str, client: httpx.AsyncClient) -> str:
    """
    Fetch *url* and return a data URI string, or raise on failure/rejection.
    Callers use return_exceptions=True so exceptions are treated as skips.
    """
    response = await client.get(url)

    if response.status_code != 200:
        raise ValueError(f"HTTP {response.status_code}")

    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    if not content_type.startswith("image/"):
        raise ValueError(f"Non-image content-type: {content_type!r}")

    if len(response.content) > _MAX_IMAGE_BYTES:
        raise ValueError(f"Image too large: {len(response.content)} bytes")

    b64 = base64.b64encode(response.content).decode()
    return f"data:{content_type};base64,{b64}"
