"""The readiness check behind ``GET /ready``: can this replica serve chat right now."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from alembic.script import ScriptDirectory
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

# A check that hangs makes the replica as useless as one that fails.
CHECK_TIMEOUT_S = 2.0
ALEMBIC_DIR = Path(__file__).resolve().parents[2] / "alembic"


class NotReady(Exception):
    """A check reached its service, but the service isn't ready yet. The message says why."""


def migration_head() -> str | None:
    """Return the newest revision in ``alembic/versions``."""
    return ScriptDirectory(str(ALEMBIC_DIR)).get_current_head()


class Readiness:
    """Checks Postgres, the schema revision and the knowledge base collection.

    Args:
        engine: The app's database engine.
        qdrant: The app's Qdrant client.
        collection: The knowledge base collection the search tool reads.
        head: The revision the schema must be at, from :func:`migration_head`.
    """

    def __init__(
        self, engine: AsyncEngine, qdrant: AsyncQdrantClient, collection: str, head: str | None
    ) -> None:
        self._engine = engine
        self._qdrant = qdrant
        self._collection = collection
        self._head = head

    async def check(self) -> dict[str, str]:
        """Run all checks at once, each with a timeout.

        Returns:
            Each check's result: ``ok``, or a short reason it isn't. Error details go
            only to the log, because the endpoint is public.
        """
        checks = {
            "postgres": self._postgres,
            "migrations": self._migrations,
            "qdrant": self._knowledge_base,
        }
        results = await asyncio.gather(*(_run(name, check) for name, check in checks.items()))
        return dict(zip(checks, results, strict=True))

    async def _postgres(self) -> None:
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def _migrations(self) -> None:
        try:
            async with self._engine.connect() as conn:
                revision = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        except ProgrammingError as exc:
            raise NotReady("not migrated") from exc
        if revision != self._head:
            raise NotReady(f"at {revision}, head is {self._head}")

    async def _knowledge_base(self) -> None:
        if not await self._qdrant.collection_exists(self._collection):
            raise NotReady("no collection")
        info = await self._qdrant.get_collection(self._collection)
        if not info.points_count:
            raise NotReady("empty collection")


async def _run(name: str, check: Callable[[], Awaitable[None]]) -> str:
    try:
        await asyncio.wait_for(check(), CHECK_TIMEOUT_S)
    except NotReady as exc:
        return str(exc)
    except TimeoutError:
        return "timeout"
    except Exception as exc:
        logger.warning("Readiness check %s failed: %r", name, exc)
        return "unavailable"
    return "ok"
