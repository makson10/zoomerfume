"""Qdrant storage for knowledge base chunks: the collection, upserts and deletes."""

from __future__ import annotations

import asyncio
import time
import uuid

from qdrant_client import AsyncQdrantClient, models

from app.kb.chunking import Chunk
from app.kb.corpus import Record

# HNSW graph: 16 links per node, 100 candidates considered while building it.
HNSW_CONFIG = models.HnswConfigDiff(m=16, ef_construct=100)
# Qdrant builds the HNSW graph only for segments bigger than this many kilobytes of vectors
# and searches smaller ones by brute force. The server default (10,000 kB in Qdrant 1.19) is
# bigger than our whole corpus; one 1536-dimension vector is about 6 kB, so 10 kB indexes
# any real segment.
INDEXING_THRESHOLD_KB = 10
PAYLOAD_INDEXES = {
    "record_id": models.PayloadSchemaType.KEYWORD,
    "type": models.PayloadSchemaType.KEYWORD,
    "price": models.PayloadSchemaType.INTEGER,
}


def point_id(record_id: str, chunk_index: int) -> str:
    """The point id of a chunk. The same chunk always gets the same id, so re-runs overwrite."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"zoomerfume:kb:{record_id}:{chunk_index}"))


async def ensure_collection(client: AsyncQdrantClient, name: str, dimensions: int) -> bool:
    """Create the collection and its payload indexes if they don't exist.

    Returns:
        True if the collection was created now, False if it already existed.
    """
    if await client.collection_exists(name):
        return False
    await client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
        hnsw_config=HNSW_CONFIG,
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=INDEXING_THRESHOLD_KB),
    )
    for field, schema in PAYLOAD_INDEXES.items():
        await client.create_payload_index(name, field, field_schema=schema, wait=True)
    return True


async def replace_record_chunks(
    client: AsyncQdrantClient,
    name: str,
    record: Record,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> None:
    """Upsert a record's chunks, then delete chunks left over from a longer old version."""
    header = record.header
    payload = {
        "source": record.source,
        "title": header.title,
        "record_id": header.id,
        "type": header.type,
        "updated": header.updated.isoformat(),
    }
    if header.price is not None:
        payload["price"] = header.price
    points = [
        models.PointStruct(
            id=point_id(header.id, chunk.index),
            vector=vector,
            payload={
                **payload,
                "chunk_index": chunk.index,
                "section": chunk.breadcrumb,
                "text": chunk.text,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    await client.upsert(name, points=points, wait=True)
    stale = models.Filter(
        must=[
            models.FieldCondition(key="record_id", match=models.MatchValue(value=header.id)),
            models.FieldCondition(key="chunk_index", range=models.Range(gte=len(chunks))),
        ]
    )
    await client.delete(name, points_selector=models.FilterSelector(filter=stale), wait=True)


async def delete_record_chunks(client: AsyncQdrantClient, name: str, record_id: str) -> None:
    """Delete every chunk of a record."""
    selector = models.FilterSelector(
        filter=models.Filter(
            must=[models.FieldCondition(key="record_id", match=models.MatchValue(value=record_id))]
        )
    )
    await client.delete(name, points_selector=selector, wait=True)


async def wait_until_indexed(
    client: AsyncQdrantClient, name: str, timeout_s: float = 60
) -> models.CollectionInfo:
    """Wait until Qdrant has finished optimizing the collection (building its HNSW graph).

    Returns the collection info at that point, or after ``timeout_s`` seconds at the latest.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        await asyncio.sleep(1)
        info = await client.get_collection(name)
        if info.status == models.CollectionStatus.GREEN or time.monotonic() > deadline:
            return info
