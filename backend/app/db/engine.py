"""Async SQLAlchemy engine for the app database.

The app lifespan creates the engine and disposes it on shutdown. Nothing connects
until the first query.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings


def create_db_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine from the database settings."""
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,  # drop stale connections instead of erroring
    )
