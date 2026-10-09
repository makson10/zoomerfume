"""Fixed-window rate limits stored in Postgres, so they hold across API replicas."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RateLimit

WINDOW = timedelta(minutes=1)
KEEP_ROWS_FOR = timedelta(days=1)


class RateLimiter:
    """Counts requests per key in fixed one-minute windows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def hit(self, key: str, limit: int) -> int | None:
        """Count one request for ``key``.

        One atomic upsert bumps the counter, so parallel requests can't both slip
        under the limit. When a key opens a new window, rows older than a day are
        deleted.

        Args:
            key: Who is counted, e.g. ``chat:user:<id>``.
            limit: How many requests the key may make per window.

        Returns:
            ``None`` when the request is within the limit, otherwise the seconds
            until the window resets.
        """
        now = datetime.now(UTC)
        window_start = now.replace(second=0, microsecond=0)
        stmt = insert(RateLimit).values(key=key, window_start=window_start, count=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=[RateLimit.key, RateLimit.window_start],
            set_={"count": RateLimit.count + 1},
        ).returning(RateLimit.count)
        count = await self._session.scalar(stmt)
        if count == 1:
            await self._session.execute(
                delete(RateLimit).where(RateLimit.window_start < now - KEEP_ROWS_FOR)
            )
        await self._session.commit()
        if count <= limit:
            return None
        return math.ceil((window_start + WINDOW - now).total_seconds())
