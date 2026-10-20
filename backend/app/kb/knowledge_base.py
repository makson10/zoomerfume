"""The knowledge base as the agent's tools and the API read it."""

from __future__ import annotations

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import KbRecord
from app.kb.corpus import RecordType
from app.kb.search import Hit, search


class KnowledgeBase:
    """Searches chunks in Qdrant and reads full records from Postgres.

    Created once in the app lifespan, on the app's clients.
    """

    def __init__(
        self,
        settings: Settings,
        qdrant: AsyncQdrantClient,
        openai: AsyncOpenAI,
        sessionmaker: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._qdrant = qdrant
        self._openai = openai
        self._sessionmaker = sessionmaker

    async def search(
        self, query: str, k: int, record_type: RecordType | None, max_price: int | None
    ) -> list[Hit]:
        """Return the ``k`` chunks closest in meaning to the query, best first."""
        return await search(
            self._qdrant, self._openai, self._settings, query, k, record_type, max_price
        )

    async def get_record(self, record_id: str) -> KbRecord | None:
        """Return the full record, or None when there is no record with this id."""
        async with self._sessionmaker() as session:
            return await session.get(KbRecord, record_id)
