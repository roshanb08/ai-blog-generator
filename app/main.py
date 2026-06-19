from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config.settings import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.providers.newsapi_client import NewsAPIClient
from app.providers.openrouter_client import OpenRouterClient
from app.providers.openwebui_client import OpenWebUIClient
from app.services.blog_service import BlogService
from app.services.dedup_service import DeduplicationService
from app.services.llm_service import LLMService
from app.services.news_service import NewsService

logger = get_logger(__name__)


def _build_llm_client(settings: Settings) -> OpenWebUIClient | OpenRouterClient:
    if settings.llm_provider == "openrouter":
        logger.info("LLM provider: OpenRouter", model=settings.openrouter_model)
        return OpenRouterClient(settings)
    logger.info("LLM provider: OpenWebUI", model=settings.openwebui_model)
    return OpenWebUIClient(settings)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings

    configure_logging(settings.log_level)
    logger.info("NewsBlog AI starting up", environment=settings.environment)

    news_client = NewsAPIClient(settings)
    llm_client = _build_llm_client(settings)

    dedup_service = DeduplicationService(settings)
    await dedup_service.init()

    news_service = NewsService(news_client, settings)
    llm_service = LLMService(llm_client, settings)

    app.state.blog_service = BlogService(
        news_service=news_service,
        dedup_service=dedup_service,
        llm_service=llm_service,
        settings=settings,
    )

    logger.info("All services initialised — ready to serve")

    yield

    logger.info("NewsBlog AI shutting down")
    await news_client.close()
    await llm_client.close()
    await dedup_service.close()
    logger.info("Clean shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NewsBlog AI",
        description=(
            "Automatically generates unique, SEO-optimised blog articles "
            "from the latest news using NewsAPI and an OpenWebUI-compatible LLM."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(router)

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception", path=str(request.url), error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Please try again."},
        )

    return app


app = create_app()
