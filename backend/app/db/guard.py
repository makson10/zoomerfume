"""Fail-open message-log writes: a slow or failed write is logged and skipped, so a database
problem never breaks a chat turn."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Plenty for a healthy Postgres, short enough that an outage only skips the log.
WRITE_TIMEOUT_S = 5.0


def pg_guard[T](fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T | None]]:
    """Wrap a message-log write: stop it after :data:`WRITE_TIMEOUT_S` and never raise."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T | None:
        try:
            return await asyncio.wait_for(fn(*args, **kwargs), timeout=WRITE_TIMEOUT_S)
        except Exception:
            logger.exception("message-log write failed (swallowed) | op=%s", fn.__name__)
            return None

    return wrapper
