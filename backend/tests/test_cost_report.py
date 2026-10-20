from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.models import Turn
from app.services.cost_report import NOTHING_YET, cost_report
from app.services.usage import CallUsage, TurnUsage


def _turn(status: str, hour: int) -> Turn:
    return Turn(
        id=uuid.uuid4(), status=status, started_at=datetime(2026, 10, 20, hour, 5, tzinfo=UTC)
    )


def test_cost_report_lists_each_finished_turn_and_the_total() -> None:
    turns = [_turn("ok", 9), _turn("ok", 10), _turn("running", 11)]
    usage = {
        turns[0].id: TurnUsage.of([CallUsage("chat", "gpt-6-luna", 2000, 0, 1800, 40)]),
        turns[1].id: TurnUsage.of(
            [
                CallUsage("chat", "gpt-6-luna", 2200, 1800, 300, 20),
                CallUsage("embedding", "text-embedding-3-small", 10),
                CallUsage("chat", "gpt-6-luna", 4000, 2100, 1800, 100),
            ]
        ),
    }

    lines = cost_report(turns, usage).splitlines()

    assert lines[4:7] == [
        "| 1 | 12:05 | 1 | 2,000 | 0 | 1,800 | 40 | $0.000265 |",
        "| 2 | 13:05 | 2 | 6,200 | 3,900 | 2,100 | 120 | $0.000382 |",
        "| **Total** |  | 3 | 8,200 | 3,900 | 3,900 | 160 | $0.000647 |",
    ]
    assert "48% of the input tokens were read from the cache." in lines
    assert lines[-1].startswith("Turn 1 starts with a cache write")


def test_cost_report_has_nothing_to_count_before_a_finished_turn() -> None:
    assert cost_report([_turn("running", 9)], {}) == NOTHING_YET
