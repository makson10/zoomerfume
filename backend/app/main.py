"""
Application entry point: :func:`create_app` builds the FastAPI app.

Lifespan events:
  startup  → create the clients, the database engine and the turn runner;
             verify Postgres / Qdrant connectivity
  shutdown → close the clients and dispose the database engine
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable
from contextlib import asynccontextmanager

from agents import set_default_openai_client
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.runtime import TurnRunner
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.db.engine import create_db_engine, ping_db
from app.middleware.request_context import FastAPILoggingMiddleware
from app.services.clients import create_openai_client, create_qdrant_client

logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────


async def _safe(coro: Awaitable[object], *, success: str, failure: str) -> None:
    """Await one shutdown step, logging success/failure and swallowing errors."""
    try:
        await coro
        logger.info(success)
    except Exception:
        logger.exception(failure)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create the clients, the engine and the turn runner, and close them on shutdown."""
    settings: Settings = app.state.settings

    # ── STARTUP ───────────────────────────────────────────────────────────────
    logger.info("Starting Zoomerfume API…")

    openai_client = create_openai_client(settings)
    qdrant_client = create_qdrant_client(settings)
    engine = create_db_engine(settings)
    set_default_openai_client(openai_client)
    app.state.turn_runner = TurnRunner(settings, async_sessionmaker(engine, expire_on_commit=False))

    # 1. Verify Postgres connectivity (message log). Fail-open: the message log
    #    is a side-write, so an unreachable DB only loses logging, never the chat.
    if not settings.message_log_enabled:
        logger.info("Message log disabled — skipping Postgres check")
    elif await ping_db(engine):
        logger.info("Postgres is reachable for the message log")
    else:
        logger.warning("Could not reach Postgres — message-log writes will be skipped")

    # 2. Verify Qdrant connectivity.
    try:
        await qdrant_client.get_collections()
        logger.info("Qdrant is reachable at %s", settings.qdrant_url)
    except Exception:
        logger.warning("Could not reach Qdrant at %s", settings.qdrant_url)

    logger.info("Zoomerfume API is ready")

    yield  # ── Application runs here ─────────────────────────────────────────

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    logger.info("Shutting down Zoomerfume API…")

    # Each step is independent and best-effort — a failure is logged but never
    # blocks the rest of the teardown.
    await _safe(
        openai_client.close(),
        success="OpenAI client closed",
        failure="Failed to close the OpenAI client",
    )
    await _safe(
        qdrant_client.close(),
        success="Qdrant client closed",
        failure="Failed to close the Qdrant client",
    )
    await _safe(
        engine.dispose(),
        success="Database engine disposed",
        failure="Failed to dispose database engine",
    )

    logger.info("Shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Uvicorn calls it with ``--factory``.

    Args:
        settings: Settings to run with. Defaults to the environment and ``.env``.
    """
    settings = settings or get_settings()
    setup_logging(debug=settings.debug)

    app = FastAPI(
        title="Zoomerfume API",
        description="Chat API for Zoomer, the AI consultant of the Zoomerfume perfume shop.",
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(FastAPILoggingMiddleware)
    app.include_router(health_router)
    app.include_router(chat_router)
    return app
