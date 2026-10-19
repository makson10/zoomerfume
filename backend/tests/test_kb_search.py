from __future__ import annotations

from qdrant_client import models

from app.kb.search import build_filter
from app.kb.store import point_id


def test_point_id_is_stable_per_chunk() -> None:
    assert point_id("KB-001", 0) == point_id("KB-001", 0)
    assert len({point_id("KB-001", 0), point_id("KB-001", 1), point_id("KB-002", 0)}) == 3


def test_build_filter_without_filters_is_none() -> None:
    assert build_filter() is None


def test_build_filter_combines_type_and_max_price() -> None:
    query_filter = build_filter("product", 3000)

    assert query_filter == models.Filter(
        must=[
            models.FieldCondition(key="type", match=models.MatchValue(value="product")),
            models.FieldCondition(key="price", range=models.Range(lte=3000)),
        ]
    )
