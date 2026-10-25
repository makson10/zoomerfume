from __future__ import annotations

from qdrant_client import models

from app.kb.search import build_filter


def test_build_filter_combines_type_and_max_price() -> None:
    query_filter = build_filter("product", 3000)

    assert build_filter() is None
    assert query_filter == models.Filter(
        must=[
            models.FieldCondition(key="type", match=models.MatchValue(value="product")),
            models.FieldCondition(key="price", range=models.Range(lte=3000)),
        ]
    )
