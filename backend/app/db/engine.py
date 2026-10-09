"""Async SQLAlchemy engine for the app database.

The app lifespan creates the engine and disposes it on shutdown. Nothing connects
until the first query.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings

logger = logging.getLogger(__name__)


def create_db_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine from the database settings."""
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,  # drop stale connections instead of erroring
    )


async def ping_db(engine: AsyncEngine) -> bool:
    """Best-effort connectivity check (``SELECT 1``); never raises."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database ping failed")
        return False
