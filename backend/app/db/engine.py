"""Lazy singleton async SQLAlchemy engine + session factory.

A module-global created once under an ``asyncio.Lock`` (double-checked), opened
in the app lifespan and disposed on shutdown. Nothing connects at import time, so
importing this module is cheap and side-effect free.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_init_lock = asyncio.Lock()


async def get_engine() -> AsyncEngine:
    """Return the shared async engine, creating it on first use."""
    global _engine, _sessionmaker
    if _engine is not None:
        return _engine
    async with _init_lock:
        if _engine is None:
            _engine = create_async_engine(
                settings.database_url,
                echo=settings.db_echo,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_pre_ping=True,  # drop stale connections instead of erroring
            )
            _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
            logger.info("SQLAlchemy async engine created")
    return _engine


async def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the shared session factory (initialising the engine if needed)."""
    if _sessionmaker is None:
        await get_engine()
    assert _sessionmaker is not None  # set in lockstep with _engine above
    return _sessionmaker


async def ping_db() -> bool:
    """Best-effort connectivity check (``SELECT 1``); never raises."""
    try:
        engine = await get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database ping failed")
        return False


async def close_engine() -> None:
    """Dispose the engine and release pooled connections."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
        logger.info("SQLAlchemy engine disposed")
