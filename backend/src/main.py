"""FastAPI application entry point for the MS Learn Video Documenter Agent."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.api.websocket import ws_router
from src.config import get_settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown."""
    settings = get_settings()
    logger.info(
        "app.startup",
        mode=settings.processing_mode,
        model=settings.foundry_model,
        host=settings.host,
        port=settings.port,
    )
    yield
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="MS Learn Video Documenter Agent",
        description="AI-powered agent that transforms screen recording videos into MS Learn-style documentation",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS — permissive for local development, tighten in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    app.include_router(router, prefix="/api/v1")
    app.include_router(ws_router, prefix="/api/v1")

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=True,
    )
