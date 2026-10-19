from __future__ import annotations

import uuid
from typing import Any

import pytest
from agents import SQLiteSession, set_tracing_disabled
from agents.testing import ScriptedModel, assistant_message, function_call

from app.agent import runtime
from app.agent.runtime import FALLBACK_TEXT, MAX_STEPS_TEXT, TurnRunner, window_history
from app.core.config import Settings
from app.db.engine import create_db_engine
from tests.fakes import FakeKnowledgeBase, make_hit


def _user(text: str) -> dict[str, Any]:
    return {"role": "user", "content": text}


def _assistant(text: str) -> dict[str, Any]:
    return {"role": "assistant", "content": text}


def test_window_history_keeps_the_last_turns_whole() -> None:
    history = [
        _user("hi"),
        _assistant("hello"),
        _user("I like vanilla"),
        _user("and something light"),
        {"type": "function_call", "call_id": "c1", "name": "search", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "c1", "output": "[]"},
        _assistant("try a vanilla musk"),
        _user("thanks"),
        _assistant("anytime"),
    ]
    new_items = [_user("one more question")]

    windowed = window_history(history, new_items, turns=2)

    assert windowed == history[2:] + new_items


@pytest.mark.parametrize("turns", [0, 5], ids=["window-off", "short-history"])
def test_window_history_keeps_everything(turns: int) -> None:
    history = [_user("hi"), _assistant("hello")]
    new_items = [_user("bye")]

    assert window_history(history, new_items, turns=turns) == history + new_items


@pytest.fixture
def runner(
    settings: Settings, fake_kb: FakeKnowledgeBase, monkeypatch: pytest.MonkeyPatch
) -> TurnRunner:
    """A turn runner with in-memory history. Each test scripts its model on ``runner.agent``."""
    set_tracing_disabled(True)
    monkeypatch.setattr(
        runtime, "SQLAlchemySession", lambda session_id, **_: SQLiteSession(session_id)
    )
    return TurnRunner(settings, create_db_engine(settings), fake_kb)


def _search_call(call_id: str) -> Any:
    args = {"query": "vanilla", "k": 5, "record_type": None, "max_price": None}
    return function_call("search_kb", args, call_id=call_id)


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        ([assistant_message(" try a vanilla musk ")], "try a vanilla musk"),
        ([assistant_message("   ")], FALLBACK_TEXT),
        (RuntimeError("model is down"), FALLBACK_TEXT),
    ],
    ids=["reply", "blank", "error"],
)
async def test_turn_runner_returns_the_reply_or_the_fallback(
    runner: TurnRunner, step: Any, expected: str
) -> None:
    runner.agent.model = ScriptedModel([step])

    assert await runner.run(uuid.uuid4(), "Mary", "hi") == expected


async def test_turn_runner_answers_after_a_tool_call(
    runner: TurnRunner, fake_kb: FakeKnowledgeBase
) -> None:
    fake_kb.hits = [make_hit("KB-012")]
    model = ScriptedModel([[_search_call("c1")], [assistant_message("Try it [KB-012].")]])
    runner.agent.model = model

    reply = await runner.run(uuid.uuid4(), "Mary", "something vanilla?")

    assert reply == "Try it [KB-012]."
    assert fake_kb.searches == [("vanilla", 5, None, None)]
    model.assert_complete()


async def test_turn_runner_stops_politely_at_the_step_limit(
    runner: TurnRunner, settings: Settings, fake_kb: FakeKnowledgeBase
) -> None:
    fake_kb.hits = [make_hit("KB-012")]
    calls = settings.agent_max_turns
    runner.agent.model = ScriptedModel([[_search_call(f"c{i}")] for i in range(calls)])

    reply = await runner.run(uuid.uuid4(), "Mary", "compare everything")

    assert reply == MAX_STEPS_TEXT.format(steps=5)
    assert len(fake_kb.searches) == calls
