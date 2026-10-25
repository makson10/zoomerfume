from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.usage import CallUsage


@pytest.mark.parametrize(
    ("call", "cost"),
    [
        # 100 uncached × 0.10 + 1,800 cached × 0.01 + 100 written × 0.125 + 50 out × 0.50
        (CallUsage("chat", "gpt-6-luna", 2000, 1800, 100, 50), "0.000065500"),
        (CallUsage("embedding", "text-embedding-3-small", 1000), "0.000020000"),
        (CallUsage("chat", "gpt-unknown", 1000, 0, 0, 100), "0"),
    ],
    ids=["cache-read-and-write", "embedding", "no-price"],
)
def test_call_cost_bills_each_kind_of_token_at_its_rate(call: CallUsage, cost: str) -> None:
    assert call.cost_usd == Decimal(cost)
