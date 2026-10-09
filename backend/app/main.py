"""
Application entry point: :func:`create_app` builds the FastAPI app.

Lifespan events:
  startup  → create the clients, the database engine, the session factory and the
             turn runner; verify Postgres / Qdrant connectivity
  shutdown → close the clients and dispose the database engine
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable
from contextlib import asynccontextmanager

from agents import set_default_openai_client
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from app.agent.runtime import TurnRunner
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.errors import ApiError, api_error_handler
from app.api.health import router as health_router
from app.api.spa import mount_web_chat
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.db.engine import create_db_engine, ping_db
from app.middleware.request_context import FastAPILoggingMiddleware
from app.services.clients import create_openai_client, create_qdrant_client

logger = logging.getLogger(__name__)

SESSION_MAX_AGE_S = 30 * 24 * 60 * 60


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
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    set_default_openai_client(openai_client)
    app.state.sessionmaker = sessionmaker
    app.state.turn_runner = TurnRunner(settings, sessionmaker)

    # 1. Verify Postgres connectivity. Users and conversations live there, so
    #    the API can't serve signed-in requests until it is reachable.
    if await ping_db(engine):
        logger.info("Postgres is reachable")
    else:
        logger.warning("Could not reach Postgres — sign-in and chat will fail until it is back")

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
        version="0.2.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(FastAPILoggingMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="zoomerfume_session",
        max_age=SESSION_MAX_AGE_S,
    )
    from fastapi import Request, status
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return await api_error_handler(
            request,
            ApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "INVALID_REQUEST",
                "Please check your input and try again.",
            ),
        )

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(chat_router)
    mount_web_chat(app)
    return app
