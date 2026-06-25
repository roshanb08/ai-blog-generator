from typing import Optional

from pydantic import BaseModel


class GitHubOwner(BaseModel):
    login: str
    avatar_url: str


class GitHubRepo(BaseModel):
    name: str
    full_name: str
    description: Optional[str] = None
    html_url: str
    stargazers_count: int
    language: Optional[str] = None
    topics: list[str] = []
    created_at: str
    owner: GitHubOwner


class GitHubSearchResponse(BaseModel):
    total_count: int
    items: list[GitHubRepo]
