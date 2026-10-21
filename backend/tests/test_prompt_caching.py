from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agent.input_filter import context_note
from app.agent.prompts import AGENT_INSTRUCTIONS, UNTRUSTED_DATA_RULES, instructions
from app.kb.chunking import count_tokens
from tests.fakes import HARDENED, VULNERABLE


def test_the_static_prompt_is_long_enough_to_cache() -> None:
    assert len(AGENT_INSTRUCTIONS.encode()) >= 6 * 1024
    assert count_tokens(AGENT_INSTRUCTIONS) > 1024


def test_the_untrusted_data_rules_come_only_with_the_wrapping() -> None:
    assert instructions(HARDENED) == f"{AGENT_INSTRUCTIONS}\n{UNTRUSTED_DATA_RULES}"
    assert instructions(VULNERABLE) == AGENT_INSTRUCTIONS


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 7, 1, 9, 30, tzinfo=UTC), "Now: Wednesday, 1 July 2026, 12:30 Kyiv time."),
        (
            datetime(2026, 12, 1, 9, 30, tzinfo=UTC),
            "Now: Tuesday, 1 December 2026, 11:30 Kyiv time.",
        ),
    ],
    ids=["summer", "winter"],
)
def test_the_context_note_gives_kyiv_time_and_the_name(now: datetime, expected: str) -> None:
    assert context_note(now, "Mary") == f"{expected} The customer's name is Mary."
