"""Vector search over the knowledge base.

python -m app.kb.search "something warm for winter" -k 5 --type product --max-price 3000
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from typing import get_args

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.kb.corpus import RecordType
from app.kb.embeddings import embed_texts
from app.services.clients import open_clients


@dataclass(frozen=True)
class Hit:
    """One chunk that matched a query."""

    record_id: str
    title: str
    type: str
    chunk_index: int
    section: str
    # The record's last update, e.g. "2026-09-14".
    updated: str
    score: float
    text: str
    price: int | None


def build_filter(
    record_type: RecordType | None = None, max_price: int | None = None
) -> models.Filter | None:
    """Turn the optional search filters into a Qdrant filter.

    ``max_price`` compares with a product's cheapest bottle. Only products have a price, so
    it also limits the results to products.
    """
    conditions = []
    if record_type is not None:
        conditions.append(
            models.FieldCondition(key="type", match=models.MatchValue(value=record_type))
        )
    if max_price is not None:
        conditions.append(models.FieldCondition(key="price", range=models.Range(lte=max_price)))
    return models.Filter(must=conditions) if conditions else None


async def search(
    qdrant: AsyncQdrantClient,
    openai: AsyncOpenAI,
    settings: Settings,
    query: str,
    k: int = 5,
    record_type: RecordType | None = None,
    max_price: int | None = None,
) -> tuple[list[Hit], int]:
    """Find the ``k`` chunks closest in meaning to the query, best first.

    Args:
        qdrant: The Qdrant client.
        openai: The OpenAI client, for embedding the query.
        settings: The app settings (collection and embedding model).
        query: The search text.
        k: How many chunks to return.
        record_type: Only return chunks of this record type.
        max_price: Only return products whose cheapest bottle costs at most this, in UAH.

    Returns:
        The hits, and the number of tokens the query's embedding was billed for.
    """
    vectors, tokens = await embed_texts(
        openai,
        [query],
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    response = await qdrant.query_points(
        settings.qdrant_collection,
        query=vectors[0],
        query_filter=build_filter(record_type, max_price),
        limit=k,
        with_payload=True,
    )
    hits = [
        Hit(
            record_id=point.payload["record_id"],
            title=point.payload["title"],
            type=point.payload["type"],
            chunk_index=point.payload["chunk_index"],
            section=point.payload["section"],
            updated=point.payload["updated"],
            score=point.score,
            text=point.payload["text"],
            price=point.payload.get("price"),
        )
        for point in response.points
    ]
    return hits, tokens


async def _run(settings: Settings, args: argparse.Namespace) -> list[Hit]:
    async with open_clients(settings) as (openai, qdrant):
        hits, _ = await search(
            qdrant, openai, settings, args.query, args.k, args.type, args.max_price
        )
    return hits


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the knowledge base.")
    parser.add_argument("query")
    parser.add_argument("-k", type=int, default=5, help="number of chunks (default 5)")
    parser.add_argument("--type", choices=get_args(RecordType))
    parser.add_argument("--max-price", type=int, help="products up to this price, in UAH")
    args = parser.parse_args()
    settings = get_settings()
    setup_logging(debug=settings.debug)

    for rank, hit in enumerate(asyncio.run(_run(settings, args)), start=1):
        price = f" · from {hit.price:,} ₴" if hit.price is not None else ""
        print(f"{rank}. {hit.score:.3f}  {hit.record_id}  {hit.section}{price}")
        print(f"   {' '.join(hit.text.split())[:160]}")


if __name__ == "__main__":
    main()
