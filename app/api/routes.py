import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.exceptions import (
    InsufficientArticlesError,
    LLMError,
    NewsAPIError,
    NewsAPIRateLimitError,
)
from app.core.logging import get_logger
from app.models.blog import BlogRequest, BlogResponse, HealthResponse
from app.services.blog_service import BlogService

logger = get_logger(__name__)

router = APIRouter()


def _get_blog_service(request: Request) -> BlogService:
    return request.app.state.blog_service


def _get_request_timeout(request: Request) -> int:
    return request.app.state.settings.request_timeout


@router.get("/health", response_model=HealthResponse, tags=["Monitoring"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post(
    "/generate-blog",
    response_model=BlogResponse,
    status_code=status.HTTP_200_OK,
    tags=["Blog"],
    summary="Generate a unique blog article from the latest news",
    response_description="A cohesive blog post in HTML5 format covering the latest news stories",
)
async def generate_blog(
    body: BlogRequest,
    blog_service: BlogService = Depends(_get_blog_service),
    timeout: int = Depends(_get_request_timeout),
) -> BlogResponse:
    logger.info(
        "POST /generate-blog",
        category=body.category,
        country=body.country,
        limit=body.limit,
        timeout=timeout,
    )

    try:
        return await asyncio.wait_for(
            blog_service.generate(
                category=body.category,
                country=body.country,
                limit=body.limit,
                full_html=body.full_html,
            ),
            timeout=timeout,
        )

    except asyncio.TimeoutError:
        logger.warning(
            "Request timed out",
            timeout=timeout,
            category=body.category,
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Blog generation timed out after {timeout}s. The LLM is taking too long — try a different model or retry shortly.",
        )

    except NewsAPIRateLimitError as exc:
        logger.warning("NewsAPI rate limit hit", detail=exc.detail)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="NewsAPI rate limit exceeded. Please retry after a few minutes.",
        )

    except NewsAPIError as exc:
        logger.error("NewsAPI error", message=exc.message, detail=exc.detail)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch news: {exc.message}",
        )

    except InsufficientArticlesError as exc:
        logger.warning("Insufficient articles", detail=exc.detail)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        )

    except LLMError as exc:
        logger.error("LLM error", message=exc.message, detail=exc.detail)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Blog generation failed: {exc.message}",
        )

    except Exception as exc:
        logger.exception("Unexpected error in /generate-blog", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )
