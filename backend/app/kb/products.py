"""The Qdrant products collection: one point per product with its accord and note vectors,
and the similar perfume search over it."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

from qdrant_client import AsyncQdrantClient, models

from app.kb.corpus import RecordHeader
from app.kb.scent import (
    Candidate,
    Match,
    NoteDictionary,
    ScentVector,
    rank,
    shared_accords,
    shared_notes,
)

# A gender filter keeps the perfumes for that gender and the unisex ones.
GenderFilter = Literal["men", "women"]

ACCORDS = "accords"
NOTES = "notes"
# Neighbours fetched by each vector before ranking.
CANDIDATES = 30
PAYLOAD_INDEXES = {
    "gender": models.PayloadSchemaType.KEYWORD,
    "price": models.PayloadSchemaType.INTEGER,
    "availability": models.PayloadSchemaType.KEYWORD,
}


@dataclass(frozen=True)
class SimilarProduct:
    """A product that smells like the reference, with what the two share."""

    record_id: str
    title: str
    brand: str
    gender: str
    concentration: str
    availability: str
    # The cheapest bottle, in UAH.
    price: int | None
    score: float
    accords_similarity: float
    notes_similarity: float
    shared_notes: list[str]
    shared_accords: list[str]


def product_point_id(record_id: str) -> int:
    """The point id of a product: the number in its record id, e.g. 28 for KB-028."""
    return int(record_id.removeprefix("KB-"))


async def ensure_products_collection(client: AsyncQdrantClient, name: str, accords: int) -> None:
    """Create the collection and its payload indexes if they don't exist.

    Args:
        client: The Qdrant client.
        name: The collection name.
        accords: The size of the accord vector, the number of accords in the dictionary.
    """
    if await client.collection_exists(name):
        return
    await client.create_collection(
        collection_name=name,
        vectors_config={
            ACCORDS: models.VectorParams(size=accords, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={NOTES: models.SparseVectorParams()},
    )
    for field, schema in PAYLOAD_INDEXES.items():
        await client.create_payload_index(name, field, field_schema=schema, wait=True)


async def replace_products(
    client: AsyncQdrantClient,
    name: str,
    products: list[RecordHeader],
    vectors: dict[str, ScentVector],
) -> int:
    """Upsert every product that has vectors, then delete the points of all other products.

    Returns:
        The number of products stored.
    """
    points = [
        models.PointStruct(
            id=product_point_id(product.id),
            vector={ACCORDS: vector.accords, NOTES: _sparse(vector)},
            payload={
                "record_id": product.id,
                "title": product.title,
                "brand": product.brand,
                "line": product.line,
                "gender": product.gender,
                "concentration": product.concentration,
                "availability": product.availability,
                "price": product.price,
            },
        )
        for product in products
        if (vector := vectors.get(product.id)) is not None
    ]
    await client.upsert(name, points=points, wait=True)
    stale = models.Filter(must_not=[models.HasIdCondition(has_id=[point.id for point in points])])
    await client.delete(name, points_selector=models.FilterSelector(filter=stale), wait=True)
    return len(points)


async def similar_products(
    client: AsyncQdrantClient,
    name: str,
    dictionary: NoteDictionary,
    record_id: str,
    k: int,
    max_price: int | None = None,
    gender: GenderFilter | None = None,
) -> list[SimilarProduct]:
    """Find the ``k`` products that smell most like a product, best first.

    Fetches the nearest neighbours by the accord vector and by the note vector, then ranks
    them all by the hybrid score. Discontinued products and the product itself are left out.

    Args:
        client: The Qdrant client.
        name: The products collection.
        dictionary: The note dictionary the vectors were built with.
        record_id: The product to compare with, e.g. "KB-028".
        k: How many products to return.
        max_price: Only products whose cheapest bottle costs at most this much, in UAH.
        gender: Only perfumes for this gender, and unisex ones.

    Raises:
        LookupError: The product has no point, e.g. it was added after the last ingest.
    """
    points = await client.retrieve(name, ids=[product_point_id(record_id)], with_vectors=True)
    if not points:
        raise LookupError(f"{record_id} has no point in {name}")
    reference = _scent(points[0].vector)
    query_filter = _filter(record_id, max_price, gender)
    responses = await asyncio.gather(
        *(
            client.query_points(
                name,
                query=query,
                using=using,
                query_filter=query_filter,
                limit=CANDIDATES,
                with_payload=True,
                with_vectors=True,
            )
            for using, query in [(ACCORDS, reference.accords), (NOTES, _sparse(reference))]
        )
    )
    found = {point.id: point for response in responses for point in response.points}
    payloads = {point.payload["record_id"]: point.payload for point in found.values()}
    candidates = [
        Candidate(point.payload["record_id"], point.payload["line"], _scent(point.vector))
        for point in found.values()
    ]
    return [
        _similar_product(payloads[match.candidate.record_id], match, reference, dictionary)
        for match in rank(reference, candidates, k)
    ]


def _filter(record_id: str, max_price: int | None, gender: GenderFilter | None) -> models.Filter:
    must: list[models.Condition] = []
    if max_price is not None:
        must.append(models.FieldCondition(key="price", range=models.Range(lte=max_price)))
    if gender is not None:
        must.append(
            models.FieldCondition(key="gender", match=models.MatchAny(any=[gender, "unisex"]))
        )
    return models.Filter(
        must=must,
        must_not=[
            models.HasIdCondition(has_id=[product_point_id(record_id)]),
            models.FieldCondition(
                key="availability", match=models.MatchValue(value="discontinued")
            ),
        ],
    )


def _similar_product(
    payload: dict[str, Any], match: Match, reference: ScentVector, dictionary: NoteDictionary
) -> SimilarProduct:
    vector = match.candidate.vector
    return SimilarProduct(
        record_id=payload["record_id"],
        title=payload["title"],
        brand=payload["brand"],
        gender=payload["gender"],
        concentration=payload["concentration"],
        availability=payload["availability"],
        price=payload["price"],
        score=round(match.score, 3),
        accords_similarity=round(match.accords, 3),
        notes_similarity=round(match.notes, 3),
        shared_notes=shared_notes(reference, vector, dictionary),
        shared_accords=shared_accords(reference, vector, dictionary),
    )


def _sparse(vector: ScentVector) -> models.SparseVector:
    return models.SparseVector(indices=list(vector.notes), values=list(vector.notes.values()))


def _scent(vector: Any) -> ScentVector:
    """Read the two named vectors of a point Qdrant returned."""
    notes = vector[NOTES]
    return ScentVector(
        accords=vector[ACCORDS], notes=dict(zip(notes.indices, notes.values, strict=True))
    )
