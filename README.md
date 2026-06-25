# AI Blog Generator

> **One API call → a fully SEO-optimised blog post from today's news.**

AI Blog Generator is a production-ready, Dockerized REST API that fetches breaking news, deduplicates stories, and uses any OpenAI-compatible LLM to generate a cohesive, publication-ready HTML5 blog article — complete with Open Graph tags, Twitter Card, and Schema.org JSON-LD.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg?logo=docker&logoColor=white)](https://ghcr.io/roshanb08/ai-blog-generator)
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Froshanb08-0D1117.svg?logo=github)](https://ghcr.io/roshanb08/ai-blog-generator)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-compatible-6D28D9.svg)](https://openrouter.ai)

---

## Features

- **Dual content sources** — Pull from [NewsAPI.org](https://newsapi.org) headlines **or** trending GitHub repositories (set `github: true`)
- **Keyword filter** — Optional `q` parameter narrows NewsAPI headlines or GitHub repo search by keyword or phrase
- **3-layer deduplication** — URL hash → title hash → Jaccard similarity; SQLite-backed with configurable TTL
- **Dual LLM provider support** — Works with **OpenRouter** (200+ models) or any **OpenWebUI** instance out of the box
- **SEO-first output** — `<title>`, `<meta description>`, Open Graph, Twitter Card, Schema.org `NewsArticle` JSON-LD
- **Two output modes** — Full `<!DOCTYPE html>` document or bare `<article>` block for embedding
- **Production-grade** — Structured JSON logging, per-attempt timeouts, no-retry-on-timeout logic, in-memory response cache
- **Zero external dependencies at runtime** — SQLite for dedup, no Redis required

---

## Quick start

### 1. Configure your environment

```bash
curl -O https://raw.githubusercontent.com/roshanb08/ai-blog-generator/main/.env.example
mv .env.example .env
```

Open `.env` and set at minimum:

```env
NEWS_API_KEY=your_newsapi_key_here       # https://newsapi.org/register
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...             # https://openrouter.ai/keys
OPENROUTER_MODEL=google/gemma-4-31b-it:free
```

### 2. Run

**Option A — Docker run**

```bash
docker run -d \
  --name ai-blog-generator \
  --env-file .env \
  -p 8000:8000 \
  -v ai_blog_data:/data \
  --restart unless-stopped \
  ghcr.io/roshanb08/ai-blog-generator:1.0.0
```

**Option B — Docker Compose**

Create a `docker-compose.yml`:

```yaml
services:
  api:
    image: ghcr.io/roshanb08/ai-blog-generator:1.0.0
    container_name: ai-blog-generator
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ai_blog_data:/data
    restart: unless-stopped

volumes:
  ai_blog_data:
```

```bash
docker compose up -d
```

> The `ai_blog_data` volume persists the deduplication database across restarts.

### 3. Verify

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 4. Generate your first blog post

```bash
curl -s -X POST http://localhost:8000/generate-blog \
  -H "Content-Type: application/json" \
  -d '{"category": "technology", "country": "us", "limit": 5}' \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'html' in data:
    open('blog.html', 'w').write(data['html'])
    print('Saved → blog.html')
else:
    print('Error:', data.get('detail', data))
"
```

### Useful commands

```bash
docker logs -f ai-blog-generator          # live logs
docker compose down                        # stop
docker compose down -v                     # stop + wipe dedup database
```

---

## Build from source

```bash
git clone https://github.com/roshanb08/ai-blog-generator.git
cd ai-blog-generator
cp .env.example .env   # fill in your keys
docker compose up -d --build
```

---

## API reference

### `POST /generate-blog`

| Field       | Type    | Default     | Description |
|-------------|---------|-------------|-------------|
| `github`    | boolean | `false`     | `true` → source content from trending GitHub repos · `false` → use NewsAPI (default) |
| `category`  | string  | `"general"` | NewsAPI category: `business` `entertainment` `general` `health` `science` `sports` `technology` — ignored when `github: true` |
| `country`   | string  | `"us"`      | ISO 3166-1 alpha-2 country code — ignored when `github: true` |
| `q`         | string  | `null`      | Keyword filter — narrows NewsAPI headlines or GitHub repo search (e.g. `"AI"`, `"language:python"`) |
| `limit`     | int     | `5`         | Stories / repos to include (1–10) |
| `full_html` | boolean | `true`      | `true` → complete `<!DOCTYPE html>` with SEO head · `false` → bare `<article>` block, style stripped |

**Response fields**

| Field              | Description |
|--------------------|-------------|
| `title`            | SEO-optimised article title (50–60 chars) |
| `html`             | Full HTML document or bare article depending on `full_html` |
| `full_html`        | Echoes the mode used |
| `meta_description` | Meta description (150–160 chars) |
| `keywords`         | Comma-separated keywords |
| `og_title`         | Open Graph title |
| `og_description`   | Open Graph description |
| `og_image`         | First article image URL |
| `sources`          | Source URLs used (NewsAPI article URLs or GitHub repo URLs) |
| `articles_used`    | Number of stories / repos included |
| `category`         | Echoes the requested category |
| `country`          | Echoes the requested country |
| `q`                | Echoes the keyword filter if provided |

---

#### Example A — full HTML document (`full_html: true`)

Returns a ready-to-publish page with SEO `<head>`, Open Graph, Twitter Card, and Schema.org JSON-LD.

```bash
curl -s -X POST http://localhost:8000/generate-blog \
  -H "Content-Type: application/json" \
  -d '{"category": "technology", "country": "us", "limit": 5, "full_html": true}' \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'html' in data:
    open('blog.html', 'w').write(data['html'])
    print('Saved → blog.html')
else:
    print('Error:', data.get('detail', data)); sys.exit(1)
"
```

<details>
<summary>Example response</summary>

```json
{
  "title": "AI and Chips: The Tech Trends Shaping 2025",
  "html": "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n  <title>AI and Chips...</title>\n  <meta name=\"description\" content=\"...\">\n  <meta name=\"keywords\" content=\"artificial intelligence, semiconductor, ...\">\n  <meta property=\"og:type\" content=\"article\">\n  <meta property=\"og:title\" content=\"AI and Chips...\">\n  <meta name=\"twitter:card\" content=\"summary_large_image\">\n  <script type=\"application/ld+json\">{...}</script>\n</head>\n<body><article>...</article></body>\n</html>",
  "full_html": true,
  "meta_description": "From generative AI to the global chip race, here's your complete guide to tech this week.",
  "keywords": "artificial intelligence, semiconductor, OpenAI, chip shortage, LLM",
  "og_title": "AI and Chips: The Tech Trends Shaping 2025",
  "og_description": "A deep dive into this week's biggest tech stories — from frontier models to the US-China chip rivalry.",
  "og_image": "https://cdn.example.com/chip.jpg",
  "sources": [
    "https://techcrunch.com/2025/...",
    "https://arstechnica.com/2025/..."
  ],
  "articles_used": 5,
  "category": "technology",
  "country": "us"
}
```
</details>

---

#### Example B — embeddable article block (`full_html: false`)

Returns only the `<article>` element with styles stripped — drop it into your existing page.

```bash
curl -s -X POST http://localhost:8000/generate-blog \
  -H "Content-Type: application/json" \
  -d '{"category": "technology", "country": "us", "limit": 5, "full_html": false}' \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'html' in data:
    open('article.html', 'w').write(data['html'])
    print('Saved → article.html')
else:
    print('Error:', data.get('detail', data)); sys.exit(1)
"
```

<details>
<summary>Example response</summary>

```json
{
  "title": "AI and Chips: The Tech Trends Shaping 2025",
  "html": "<article>\n  <header><h1>AI and Chips...</h1></header>\n  <section><h2>...</h2><p>...</p></section>\n  ...\n</article>",
  "full_html": false,
  "meta_description": "From generative AI to the global chip race...",
  "keywords": "artificial intelligence, semiconductor, OpenAI, ...",
  "og_title": "AI and Chips: The Tech Trends Shaping 2025",
  "og_description": "A deep dive into this week's biggest tech stories...",
  "og_image": "https://cdn.example.com/chip.jpg",
  "sources": ["https://techcrunch.com/2025/...", "..."],
  "articles_used": 5,
  "category": "technology",
  "country": "us"
}
```
</details>

---

#### Example C — trending GitHub repositories (`github: true`)

Generates a developer-focused blog from the most popular new GitHub repos this week.

```bash
curl -s -X POST http://localhost:8000/generate-blog \
  -H "Content-Type: application/json" \
  -d '{"github": true, "limit": 5}' \
  | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'html' in data:
    open('github-blog.html', 'w').write(data['html'])
    print('Saved → github-blog.html')
else:
    print('Error:', data.get('detail', data)); sys.exit(1)
"
```

Filter by language or topic using `q`:

```bash
# Trending Python repos
curl -X POST http://localhost:8000/generate-blog \
  -H "Content-Type: application/json" \
  -d '{"github": true, "q": "language:python", "limit": 5}'

# Trending AI/ML repos
curl -X POST http://localhost:8000/generate-blog \
  -H "Content-Type: application/json" \
  -d '{"github": true, "q": "machine learning", "limit": 5}'
```

<details>
<summary>Example response</summary>

```json
{
  "title": "GitHub's Hottest New Repos This Week: AI Tools Taking Over",
  "html": "<!DOCTYPE html>...",
  "full_html": true,
  "meta_description": "From autonomous agents to blazing-fast vector databases, here are the GitHub projects developers are starring right now.",
  "keywords": "open source, GitHub trending, AI tools, developer tools, LLM",
  "og_title": "GitHub's Hottest New Repos This Week",
  "og_description": "The open-source projects gaining the most stars this week — and why they matter.",
  "og_image": null,
  "sources": [
    "https://github.com/owner/repo-one",
    "https://github.com/owner/repo-two"
  ],
  "articles_used": 5,
  "category": "general",
  "country": "us",
  "q": null
}
```
</details>

---

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### Interactive docs

| | URL |
|---|---|
| Swagger UI | `http://localhost:8000/docs` |
| ReDoc | `http://localhost:8000/redoc` |

---

## LLM provider setup

Set `LLM_PROVIDER` in `.env`. Only the credentials for the chosen provider are required.

### OpenRouter (recommended)

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=google/gemma-4-31b-it:free
OPENROUTER_SITE_URL=https://your-site.com   # optional
OPENROUTER_SITE_NAME=AI Blog Generator            # optional
```

Get a free key at [openrouter.ai/keys](https://openrouter.ai/keys). Tested free models:

| Model | Speed | Notes |
|-------|-------|-------|
| `google/gemma-4-31b-it:free` | ~25s | Recommended — reliable HTML output |
| `openai/gpt-oss-20b:free` | ~20s | Fast, good instruction following |
| `nvidia/nemotron-3-super-120b-a12b:free` | ~30s | Larger, higher quality |

### OpenWebUI

```env
LLM_PROVIDER=openwebui
OPENWEBUI_BASE_URL=https://your-openwebui-instance.com
OPENWEBUI_API_KEY=your_key
OPENWEBUI_MODEL=gpt-4o
```

---

## Environment variables

### Required

| Variable       | Description |
|----------------|-------------|
| `NEWS_API_KEY` | [newsapi.org](https://newsapi.org/register) API key |
| `LLM_PROVIDER` | `openrouter` or `openwebui` |

### OpenRouter

| Variable               | Default           | Description |
|------------------------|-------------------|-------------|
| `OPENROUTER_API_KEY`   | —                 | API key |
| `OPENROUTER_MODEL`     | `openai/gpt-4o`   | Model ID |
| `OPENROUTER_SITE_URL`  | _(empty)_         | Sent as `HTTP-Referer` |
| `OPENROUTER_SITE_NAME` | `AI Blog Generator`     | Sent as `X-Title` |

### OpenWebUI

| Variable             | Default   | Description |
|----------------------|-----------|-------------|
| `OPENWEBUI_API_KEY`  | —         | API key |
| `OPENWEBUI_BASE_URL` | —         | Instance URL (no trailing slash) |
| `OPENWEBUI_MODEL`    | `gpt-4o`  | Model name |

### LLM behaviour

| Variable          | Default | Description |
|-------------------|---------|-------------|
| `LLM_TIMEOUT`     | `90`    | Per-attempt HTTP timeout (seconds) |
| `LLM_TEMPERATURE` | `0.7`   | Sampling temperature (0 = deterministic) |
| `LLM_MAX_TOKENS`  | `2048`  | Max response tokens — free models use ~600–900 |
| `REQUEST_TIMEOUT` | `120`   | Total wall-clock budget for `/generate-blog` |

### GitHub

| Variable       | Default | Description |
|----------------|---------|-------------|
| `GITHUB_TOKEN` | _(none)_ | Optional PAT — raises rate limit from 10 to 30 req/min. No scopes needed. [Create one](https://github.com/settings/tokens) |

### Deduplication

| Variable                           | Default          | Description |
|------------------------------------|------------------|-------------|
| `DEDUP_DB_PATH`                    | `/data/dedup.db` | SQLite DB path inside container |
| `DEDUP_TITLE_SIMILARITY_THRESHOLD` | `0.65`           | Jaccard similarity threshold (0–1) |
| `DEDUP_TTL_HOURS`                  | `48`             | Hours before a seen article is eligible again |

### Cache & app

| Variable          | Default      | Description |
|-------------------|--------------|-------------|
| `CACHE_ENABLED`   | `true`       | In-memory response cache |
| `CACHE_TTL_SECONDS` | `300`      | Cache TTL in seconds |
| `MAX_NEWS_FETCH`  | `20`         | Articles fetched from NewsAPI per request |
| `LOG_LEVEL`       | `info`       | `debug` `info` `warning` `error` |
| `ENVIRONMENT`     | `production` | `development` or `production` |

---

## Architecture

```
┌─────────────┐       ┌──────────────────────────────────────────────────┐
│   Client    │──────▶│  FastAPI  (POST /generate-blog)                  │
└─────────────┘       │                                                  │
                      │  BlogService (pipeline orchestrator)             │
                      │    │                                              │
                      │    ├─ NewsService ──▶ NewsAPIClient               │
                      │    │                  (httpx + retry)             │
                      │    │                                              │
                      │    ├─ DeduplicationService                        │
                      │    │   URL hash · title hash · Jaccard sim        │
                      │    │   SQLite persistence + TTL                   │
                      │    │                                              │
                      │    └─ LLMService ──▶ OpenRouterClient             │
                      │                   or OpenWebUIClient              │
                      │                      (httpx + retry)             │
                      └──────────────────────────────────────────────────┘
                                            │
                                      ┌─────┴─────┐
                                      │  /data/   │
                                      │  dedup.db │  (Docker volume)
                                      └───────────┘
```

```
app/
├── api/routes.py             FastAPI router + error handling
├── config/settings.py        Pydantic-settings (env → typed config)
├── core/
│   ├── exceptions.py         Custom exception hierarchy
│   └── logging.py            Structured JSON logging (structlog)
├── models/
│   ├── blog.py               BlogRequest / BlogResponse
│   └── news.py               NewsArticle / NewsAPIResponse
├── providers/
│   ├── newsapi_client.py     Async NewsAPI client (retry)
│   ├── openrouter_client.py  Async OpenRouter client (retry)
│   └── openwebui_client.py   Async OpenWebUI client (retry)
├── services/
│   ├── blog_service.py       Pipeline orchestrator + cache
│   ├── dedup_service.py      3-layer deduplication engine
│   ├── llm_service.py        Prompt builder + response parser
│   └── news_service.py       Fetch + normalise articles
├── utils/
│   ├── html_utils.py         HTML extraction, SEO doc builder
│   └── image_utils.py        Base64 image embedding
└── main.py                   FastAPI app + lifespan
```

---

## Deduplication design

Three checks applied in order (cheapest first — short-circuits on first match):

1. **URL hash** — SHA-256 of the article URL
2. **Title hash** — SHA-256 of the normalised, lowercased, punctuation-stripped title
3. **Jaccard similarity** — word-set overlap on tokenised titles, stop words removed; configurable threshold (default 0.65)

All seen articles are persisted in SQLite with a TTL (default 48 h), so deduplication survives container restarts without re-serving old content.

---

## CI / CD

The included GitHub Actions workflow (`.github/workflows/docker-publish.yml`) automatically builds and pushes a multi-platform image (`linux/amd64` + `linux/arm64`) to Docker Hub on every push to `main` and on version tags.

**Setup — add these two secrets to your GitHub repository:**

| Secret               | Value |
|----------------------|-------|
| `DOCKERHUB_USERNAME` | Your Docker Hub username |
| `DOCKERHUB_TOKEN`    | Docker Hub access token (Settings → Security → New Access Token) |

Releases are tagged by pushing a git tag:

```bash
git tag v1.0.0
git push origin v1.0.0
# Publishes: ghcr.io/roshanb08/ai-blog-generator:1.0.0, :1.0, :latest
```

---

## Performance notes

| Concern | Approach |
|---------|----------|
| LLM latency | 90 s per-attempt timeout; timeouts are **not retried** (avoids doubling wait on dead models); 120 s total request budget |
| Free model reliability | `google/gemma-4-31b-it:free` and `openai/gpt-oss-20b:free` tested at ~20–30 s per blog |
| Response caching | Same `category + country + limit + full_html` served from memory for 5 min |
| Dedup at scale | Swap SQLite for Redis + Bloom filter; `DeduplicationService` interface is unchanged |
| Concurrency | `uvicorn --workers 2`; scale horizontally behind a load balancer |

---

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

---

## License

MIT — see [LICENSE](LICENSE).
