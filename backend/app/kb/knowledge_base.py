"""The knowledge base as the agent's tools and the API read it."""

from __future__ import annotations

import re

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.models import KbRecord
from app.kb.corpus import RECORD_ID_PATTERN, RecordType
from app.kb.products import GenderFilter, SimilarProduct, similar_products
from app.kb.records import find_product
from app.kb.scent import NoteDictionary
from app.kb.search import Hit, search
from app.services.usage import CallUsage


class KnowledgeBase:
    """Searches chunks and products in Qdrant and reads full records from Postgres.

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
        self._notes = NoteDictionary.load()

    async def search(
        self, query: str, k: int, record_type: RecordType | None, max_price: int | None
    ) -> tuple[list[Hit], CallUsage]:
        """Return the ``k`` chunks closest in meaning to the query, best first, and the usage
        of the query's embedding call."""
        hits, tokens = await search(
            self._qdrant, self._openai, self._settings, query, k, record_type, max_price
        )
        return hits, CallUsage("embedding", self._settings.embedding_model, tokens)

    async def get_record(self, record_id: str) -> KbRecord | None:
        """Return the full record, or None when there is no record with this id."""
        async with self._sessionmaker() as session:
            return await session.get(KbRecord, record_id)

    async def find_product(self, name: str) -> KbRecord | None:
        """Return the product with this record id, or the one whose title matches the name
        best. None when there is no such product."""
        async with self._sessionmaker() as session:
            if re.fullmatch(RECORD_ID_PATTERN, name):
                record = await session.get(KbRecord, name)
                return record if record is not None and record.type == "product" else None
            return await find_product(session, name)

    async def similar_products(
        self,
        record_id: str,
        k: int,
        max_price: int | None,
        gender: GenderFilter | None,
    ) -> list[SimilarProduct]:
        """Return the ``k`` products that smell most like the product, best first."""
        return await similar_products(
            self._qdrant,
            self._settings.qdrant_products_collection,
            self._notes,
            record_id,
            k,
            max_price,
            gender,
        )
