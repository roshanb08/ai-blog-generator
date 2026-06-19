from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── NewsAPI ───────────────────────────────────────────────────────────────
    news_api_key: str = Field(..., description="NewsAPI.org API key")
    news_api_base_url: str = "https://newsapi.org/v2"
    news_api_timeout: int = 15
    news_api_max_retries: int = 3

    # ── LLM provider selection ────────────────────────────────────────────────
    llm_provider: Literal["openwebui", "openrouter"] = Field(
        default="openwebui",
        description="Which LLM backend to use: 'openwebui' or 'openrouter'",
    )

    # ── Shared LLM behaviour ──────────────────────────────────────────────────
    llm_timeout: int = 90          # per-attempt httpx timeout (seconds)
    llm_max_retries: int = 1       # retries on non-timeout errors only
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048     # free models use ~600-900 tokens; 2048 is safe ceiling

    # ── Request timeout ───────────────────────────────────────────────────────
    request_timeout: int = 120     # total wall-clock budget for /generate-blog

    # ── OpenWebUI credentials ─────────────────────────────────────────────────
    openwebui_api_key: Optional[str] = Field(
        default=None, description="OpenWebUI API key (required when llm_provider=openwebui)"
    )
    openwebui_base_url: Optional[str] = Field(
        default=None, description="OpenWebUI base URL, e.g. https://your-instance.com"
    )
    openwebui_model: str = "gpt-4o"

    # ── OpenRouter credentials ────────────────────────────────────────────────
    openrouter_api_key: Optional[str] = Field(
        default=None, description="OpenRouter API key (required when llm_provider=openrouter)"
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o"
    openrouter_site_url: str = ""   # sent as HTTP-Referer; helps OpenRouter attribution
    openrouter_site_name: str = "AI Blog Generator"  # sent as X-Title

    # ── Deduplication ─────────────────────────────────────────────────────────
    dedup_db_path: str = "/data/dedup.db"
    dedup_title_similarity_threshold: float = 0.65
    dedup_ttl_hours: int = 48

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300

    # ── App ───────────────────────────────────────────────────────────────────
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    environment: Literal["development", "production"] = "production"
    max_news_fetch: int = 20
    default_article_limit: int = 5

    @field_validator("openwebui_base_url", mode="before")
    @classmethod
    def strip_trailing_slash(cls, v: object) -> Optional[str]:
        if v is None:
            return None
        return str(v).rstrip("/")

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> "Settings":
        if self.llm_provider == "openwebui":
            missing = [
                name for name, val in [
                    ("OPENWEBUI_API_KEY", self.openwebui_api_key),
                    ("OPENWEBUI_BASE_URL", self.openwebui_base_url),
                ]
                if not val
            ]
            if missing:
                raise ValueError(
                    f"llm_provider=openwebui requires: {', '.join(missing)}"
                )
        elif self.llm_provider == "openrouter":
            if not self.openrouter_api_key:
                raise ValueError(
                    "llm_provider=openrouter requires OPENROUTER_API_KEY"
                )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
