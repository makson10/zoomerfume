"""
Application entry point.

Lifespan events:
  startup  → verify Postgres / Qdrant connectivity
  shutdown → close the shared clients and the database engine
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable
from contextlib import asynccontextmanager

from agents import set_default_openai_client
from fastapi import FastAPI

from app.agent.runtime import TurnRunner
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.engine import close_engine, get_sessionmaker, ping_db
from app.middleware.request_context import FastAPILoggingMiddleware
from app.services.clients import close_clients, get_openai_client, get_qdrant_client

settings = get_settings()
setup_logging(debug=settings.debug)
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
    """Manage application startup and shutdown tasks."""

    # ── STARTUP ───────────────────────────────────────────────────────────────
    logger.info("Starting Zoomerfume API…")

    set_default_openai_client(get_openai_client())
    app.state.turn_runner = TurnRunner(settings, await get_sessionmaker())

    # 1. Verify Postgres connectivity (message log). Fail-open: the message log
    #    is a side-write, so an unreachable DB only loses logging, never the chat.
    if not settings.message_log_enabled:
        logger.info("Message log disabled — skipping Postgres check")
    elif await ping_db():
        logger.info("Postgres is reachable for the message log")
    else:
        logger.warning("Could not reach Postgres — message-log writes will be skipped")

    # 2. Verify Qdrant connectivity.
    try:
        await get_qdrant_client().get_collections()
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
        close_clients(),
        success="Shared clients closed",
        failure="Failed to close shared clients",
    )
    await _safe(
        close_engine(),
        success="Database engine disposed",
        failure="Failed to dispose database engine",
    )

    logger.info("Shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Zoomerfume API",
    description="Chat API for Zoomer, the AI consultant of the Zoomerfume perfume shop.",
    version="0.1.0",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

app.add_middleware(FastAPILoggingMiddleware)
app.include_router(health_router)
app.include_router(chat_router)
