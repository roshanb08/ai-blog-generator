from typing import Any


class NewsBlogError(Exception):
    """Base exception for all NewsBlog AI errors."""

    def __init__(self, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class NewsAPIError(NewsBlogError):
    """Raised when NewsAPI returns an error or times out."""


class NewsAPIRateLimitError(NewsAPIError):
    """Raised when NewsAPI rate limit is exceeded."""


class LLMError(NewsBlogError):
    """Raised when the LLM provider returns an error."""


class LLMResponseParseError(LLMError):
    """Raised when the LLM response cannot be parsed into valid HTML."""


class InsufficientArticlesError(NewsBlogError):
    """Raised when there are not enough unique articles after deduplication."""


class DeduplicationError(NewsBlogError):
    """Raised on database or deduplication failures."""
