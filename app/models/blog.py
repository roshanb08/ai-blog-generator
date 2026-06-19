from typing import Optional

from pydantic import BaseModel, Field


class BlogRequest(BaseModel):
    category: str = Field(
        default="general",
        description="News category: business, entertainment, general, health, science, sports, technology",
    )
    country: str = Field(default="us", description="2-letter ISO country code")
    limit: int = Field(default=5, ge=1, le=10, description="Number of news stories to include")
    full_html: bool = Field(
        default=True,
        description=(
            "True → complete <!DOCTYPE html> document with SEO head, Open Graph, "
            "Twitter Card, and Schema.org JSON-LD. "
            "False → bare <article> block only, <style> stripped for embedding."
        ),
    )


class BlogResponse(BaseModel):
    # Core content
    title: str
    html: str
    full_html: bool

    # SEO fields
    meta_description: Optional[str] = None
    keywords: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None

    # Provenance
    sources: list[str]
    articles_used: int
    category: str
    country: str


class HealthResponse(BaseModel):
    status: str = "ok"
