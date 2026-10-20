from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.usage import CallUsage, TurnUsage


@pytest.mark.parametrize(
    ("call", "cost"),
    [
        # 100 uncached × 0.10 + 1,800 cached × 0.01 + 100 written × 0.125 + 50 out × 0.50
        (CallUsage("chat", "gpt-6-luna", 2000, 1800, 100, 50), "0.000065500"),
        (CallUsage("chat", "gpt-6-luna", 1, 0, 1, 0), "0.000000125"),
        (CallUsage("embedding", "text-embedding-3-small", 1000), "0.000020000"),
        (CallUsage("chat", "gpt-unknown", 1000, 0, 0, 100), "0"),
    ],
    ids=["cache-read-and-write", "one-written-token", "embedding", "no-price"],
)
def test_call_cost_bills_each_kind_of_token_at_its_rate(call: CallUsage, cost: str) -> None:
    assert call.cost_usd == Decimal(cost)


def test_turn_usage_counts_chat_calls_and_every_cost() -> None:
    calls = [
        CallUsage("chat", "gpt-6-luna", 2000, 0, 1800, 40),
        CallUsage("embedding", "text-embedding-3-small", 10),
        CallUsage("chat", "gpt-6-luna", 2600, 1800, 600, 60),
    ]

    usage = TurnUsage.of(calls)

    assert usage == TurnUsage(
        calls=2,
        input_tokens=4600,
        cached_tokens=1800,
        cache_write_tokens=2400,
        output_tokens=100,
        cost_usd=sum((call.cost_usd for call in calls), Decimal(0)),
    )
    assert usage.model_dump(mode="json")["cost_usd"] == "0.000408200"
