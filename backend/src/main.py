"""FastAPI application entry point for the MS Learn Video Documenter Agent."""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

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


async def cli_process(video_path: str, doc_type: str, output_dir: str) -> None:
    """CLI entry point for processing a video into documentation."""
    from src.agents.orchestrator import PipelineInput, run_pipeline
    from src.models.document import DocType

    request = PipelineInput(
        video_source=video_path,
        doc_type=DocType(doc_type),
    )

    events = await run_pipeline.run(request)
    result = events[-1].data

    # Save output
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    doc_path = out / f"{result.document.document_id}.md"
    doc_path.write_text(result.document.markdown_content, encoding="utf-8")

    # Copy media files
    media_dir = out / "media"
    media_dir.mkdir(exist_ok=True)
    for screenshot in result.document.media_files:
        src_path = Path(screenshot.source_path)
        if src_path.exists():
            shutil.copy2(src_path, media_dir / src_path.name)

    print(f"Document saved to {doc_path}")
    score = result.evaluation.scores.overall
    status = "PASSED" if result.evaluation.passed else "FAILED"
    print(f"Quality score: {score:.2f} ({status})")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "process":
        parser = argparse.ArgumentParser(description="MS Learn Video Documenter")
        sub = parser.add_subparsers(dest="command")
        process_parser = sub.add_parser("process", help="Process a video into documentation")
        process_parser.add_argument("video_path", help="Path to the video file")
        process_parser.add_argument(
            "--doc-type",
            default="tutorial",
            choices=["quickstart", "tutorial", "how-to", "concept", "overview"],
        )
        process_parser.add_argument("--output", default="./output", help="Output directory")
        args = parser.parse_args()
        asyncio.run(cli_process(args.video_path, args.doc_type, args.output))
    else:
        settings = get_settings()
        uvicorn.run(
            "src.main:app",
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level,
            reload=True,
        )
