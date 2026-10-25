"""Application entry point: :func:`create_app` builds the FastAPI app."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Awaitable
from contextlib import asynccontextmanager

from agents import set_default_openai_client
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from app.agent.runtime import TurnRunner
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversations_router
from app.api.errors import ERROR_RESPONSES, ApiError, api_error_handler, validation_error_handler
from app.api.health import router as health_router
from app.api.notes import router as notes_router
from app.api.records import router as records_router
from app.api.spa import mount_web_chat
from app.api.tools import router as tools_router
from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.db.engine import create_db_engine, ping_db
from app.kb.knowledge_base import KnowledgeBase
from app.middleware.request_context import FastAPILoggingMiddleware
from app.services.clients import create_openai_client, create_qdrant_client
from app.services.notes import NoteStore

logger = logging.getLogger(__name__)

SESSION_MAX_AGE_S = 30 * 24 * 60 * 60


async def _close_quietly(name: str, closing: Awaitable[object]) -> None:
    """Await one shutdown step. A failure is only logged, so the other steps still run."""
    try:
        await closing
        logger.info("%s closed", name)
    except Exception:
        logger.exception("Failed to close the %s", name)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create the clients, the engine and the objects built on them; close them on shutdown."""
    settings: Settings = app.state.settings
    logger.info("Starting Zoomerfume API…")

    openai_client = create_openai_client(settings)
    qdrant_client = create_qdrant_client(settings)
    engine = create_db_engine(settings)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    set_default_openai_client(openai_client)
    knowledge_base = KnowledgeBase(settings, qdrant_client, openai_client, sessionmaker)
    notes = NoteStore(sessionmaker)
    app.state.sessionmaker = sessionmaker
    app.state.kb = knowledge_base
    app.state.notes = notes
    app.state.turn_runner = TurnRunner(settings, engine, knowledge_base, notes)

    if await ping_db(engine):
        logger.info("Postgres is reachable")
    else:
        logger.warning("Could not reach Postgres. Sign-in and chat fail until it is back")
    try:
        await qdrant_client.get_collections()
        logger.info("Qdrant is reachable at %s", settings.qdrant_url)
    except Exception:
        logger.warning("Could not reach Qdrant at %s", settings.qdrant_url)
    logger.info("Zoomerfume API is ready")

    yield

    logger.info("Shutting down Zoomerfume API…")
    await _close_quietly("OpenAI client", openai_client.close())
    await _close_quietly("Qdrant client", qdrant_client.close())
    await _close_quietly("database engine", engine.dispose())
    logger.info("Shutdown complete")


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
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        responses=ERROR_RESPONSES,
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
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(chat_router)
    app.include_router(records_router)
    app.include_router(tools_router)
    app.include_router(notes_router)
    mount_web_chat(app)
    return app
