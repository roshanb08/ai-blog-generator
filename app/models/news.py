from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NewsSource(BaseModel):
    id: Optional[str] = None
    name: str


class NewsArticle(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    description: Optional[str] = None
    content: Optional[str] = None
    url: str
    url_to_image: Optional[str] = Field(default=None, alias="urlToImage")
    source: NewsSource
    published_at: datetime = Field(alias="publishedAt")
    author: Optional[str] = None

    @field_validator("title", "description", "content", "url_to_image", mode="before")
    @classmethod
    def strip_and_none(cls, v: object) -> Optional[str]:
        if v is None or v == "" or v == "[Removed]":
            return None
        return str(v).strip()

    @field_validator("url", mode="before")
    @classmethod
    def ensure_url_str(cls, v: object) -> str:
        return str(v).strip()


class NewsAPIResponse(BaseModel):
    status: str
    total_results: int = Field(alias="totalResults")
    articles: list[NewsArticle]

    model_config = {"populate_by_name": True}
