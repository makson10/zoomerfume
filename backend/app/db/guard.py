"""Fail-open guard for message-log writes.

Every public write goes through :func:`pg_guard`: it no-ops when the message log
is disabled, bounds the write with a short timeout (so a stalled/unreachable
Postgres can never hang a chat turn), and swallows every error after logging.
Recording is best-effort and may never delay or break a turn.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Upper bound on a single write. Generous for a healthy local Postgres, tight
# enough that an outage degrades to "skip the log" within a few seconds.
WRITE_TIMEOUT_S = 5.0


def pg_guard[T](fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T | None]]:
    """Wrap a message-log write: gate on the flag, bound it, never raise."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T | None:
        if not settings.message_log_enabled:
            return None
        try:
            return await asyncio.wait_for(fn(*args, **kwargs), timeout=WRITE_TIMEOUT_S)
        except Exception:
            logger.exception("message-log write failed (swallowed) | op=%s", fn.__name__)
            return None

    return wrapper
