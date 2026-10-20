from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from agents import SQLiteSession, set_tracing_disabled
from agents.testing import ScriptedModel, assistant_message, function_call

from app.agent import runtime
from app.agent.citations import Citations
from app.agent.prompts import AGENT_INSTRUCTIONS
from app.agent.runtime import (
    FALLBACK_TEXT,
    MAX_STEPS_TEXT,
    NewTurn,
    TurnRunner,
    TurnStart,
    window_history,
)
from app.agent.streaming import Token, ToolCall
from app.core.config import Settings
from app.db.engine import create_db_engine
from tests.fakes import FakeKnowledgeBase, FakeNoteStore, FakeTurnStore, make_hit


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
def history() -> dict[str, SQLiteSession]:
    """Each conversation's agent history, in memory."""
    return {}


@pytest.fixture
def runner(
    settings: Settings,
    fake_kb: FakeKnowledgeBase,
    fake_notes: FakeNoteStore,
    history: dict[str, SQLiteSession],
    monkeypatch: pytest.MonkeyPatch,
) -> TurnRunner:
    """A turn runner with in-memory history. Each test scripts its model on ``runner.agent``."""
    set_tracing_disabled(True)
    monkeypatch.setattr(
        runtime,
        "SQLAlchemySession",
        lambda session_id, **_: history.setdefault(session_id, SQLiteSession(session_id)),
    )
    return TurnRunner(settings, create_db_engine(settings), fake_kb, fake_notes)


SEARCH_ARGS = {"query": "vanilla", "k": 5, "record_type": None, "max_price": None}


def _search_call(call_id: str) -> Any:
    return function_call("search_kb", SEARCH_ARGS, call_id=call_id)


async def _start(
    turns: FakeTurnStore, text: str, retrieved_before: set[str] | None = None
) -> NewTurn:
    conversation_id = uuid.uuid4()
    turn_id = await turns.start(conversation_id)
    assert turn_id is not None
    return NewTurn(turn_id, conversation_id, uuid.uuid4(), "Mary", text, retrieved_before or set())


async def _run(runner: TurnRunner, turns: FakeTurnStore, turn: NewTurn) -> list[Any]:
    return [event async for event in runner.stream(turn, turns)]


@pytest.mark.parametrize(
    ("step", "reply", "status"),
    [
        ([assistant_message(" try a vanilla musk ")], "try a vanilla musk", "ok"),
        ([assistant_message("   ")], FALLBACK_TEXT, "failed"),
        (RuntimeError("model is down"), FALLBACK_TEXT, "failed"),
    ],
    ids=["reply", "blank", "error"],
)
async def test_turn_runner_returns_the_reply_or_the_fallback(
    runner: TurnRunner, fake_turns: FakeTurnStore, step: Any, reply: str, status: str
) -> None:
    runner.agent.model = ScriptedModel([step])
    turn = await _start(fake_turns, "hi")

    *_, result = await _run(runner, fake_turns, turn)

    assert (result.reply, result.status, result.steps) == (reply, status, [])
    assert fake_turns.turns[turn.id].status == status


async def test_turn_runner_streams_a_tool_call_and_checks_citations(
    runner: TurnRunner, fake_kb: FakeKnowledgeBase, fake_turns: FakeTurnStore
) -> None:
    fake_kb.hits = [make_hit("KB-031")]
    reply = "Try KB-031 [KB-031], or KB-012 from before [KB-012], not [KB-099]."
    model = ScriptedModel([[_search_call("c1")], [assistant_message(reply)]])
    runner.agent.model = model
    turn = await _start(fake_turns, "something vanilla?", retrieved_before={"KB-012"})

    start, tool_call, step, token, result = await _run(runner, fake_turns, turn)

    assert start == TurnStart(conversation_id=turn.conversation_id, turn_id=turn.id)
    assert tool_call == ToolCall(tool="search_kb", args=SEARCH_ARGS)
    assert (step.tool, step.record_ids) == ("search_kb", ["KB-031"])
    assert token == Token(text=reply)
    assert (result.reply, result.status, result.steps) == (reply, "ok", [step])
    assert result.citations == Citations(valid=["KB-031", "KB-012"], invalid=["KB-099"])
    stored = fake_turns.turns[turn.id]
    assert (stored.status, stored.citations) == ("ok", result.citations.model_dump())
    model.assert_complete()


async def test_turn_runner_saves_notes_for_the_turns_user(
    runner: TurnRunner, fake_notes: FakeNoteStore, fake_turns: FakeTurnStore
) -> None:
    save = function_call("save_note", {"text": "Wishlist: Jazz Club"}, call_id="c1")
    runner.agent.model = ScriptedModel([[save], [assistant_message("Saved!")]])
    first = await _start(fake_turns, "add Jazz Club to my wishlist")
    second = await _start(fake_turns, "add Jazz Club to my wishlist")

    await _run(runner, fake_turns, first)
    runner.agent.model = ScriptedModel([[save], [assistant_message("Saved!")]])
    await _run(runner, fake_turns, second)

    assert [(note.user_id, note.turn_id) for note in fake_notes.notes] == [
        (first.user_id, first.id),
        (second.user_id, second.id),
    ]


async def test_turn_runner_stops_politely_at_the_step_limit(
    runner: TurnRunner, settings: Settings, fake_kb: FakeKnowledgeBase, fake_turns: FakeTurnStore
) -> None:
    fake_kb.hits = [make_hit("KB-012")]
    calls = settings.agent_max_turns
    runner.agent.model = ScriptedModel([[_search_call(f"c{i}")] for i in range(calls)])
    turn = await _start(fake_turns, "compare everything")

    *_, result = await _run(runner, fake_turns, turn)

    assert (result.reply, result.status) == (MAX_STEPS_TEXT.format(steps=5), "max_steps")
    assert len(result.steps) == len(fake_kb.searches) == calls
    assert result.citations == Citations()


async def test_a_stopped_turn_keeps_the_reply_so_far(
    runner: TurnRunner,
    fake_kb: FakeKnowledgeBase,
    fake_turns: FakeTurnStore,
    history: dict[str, SQLiteSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def never_answers(*args: Any) -> list[Any]:
        await asyncio.Event().wait()
        return []

    monkeypatch.setattr(fake_kb, "search", never_answers)
    preamble = "Let me look that up."
    runner.agent.model = ScriptedModel([[assistant_message(preamble), _search_call("c1")]])
    turn = await _start(fake_turns, "something vanilla?")

    events = runner.stream(turn, fake_turns)
    seen = [await anext(events) for _ in range(3)]
    await events.aclose()

    assert seen[1:] == [Token(text=preamble), ToolCall(tool="search_kb", args=SEARCH_ARGS)]
    assert fake_turns.turns[turn.id].status == "cancelled"
    items = await history[str(turn.conversation_id)].get_items()
    assert [(item["role"], item["content"]) for item in items] == [
        ("user", "something vanilla?"),
        ("assistant", preamble),
    ]


async def test_each_model_call_sends_the_static_prompt_first_and_the_context_note_last(
    runner: TurnRunner,
    fake_kb: FakeKnowledgeBase,
    fake_turns: FakeTurnStore,
    history: dict[str, SQLiteSession],
) -> None:
    fake_kb.hits = [make_hit("KB-031")]
    model = ScriptedModel([[_search_call("c1")], [assistant_message("Try KB-031 [KB-031].")]])
    runner.agent.model = model
    turn = await _start(fake_turns, "something vanilla?")

    await _run(runner, fake_turns, turn)

    static_prompt = {
        "role": "developer",
        "content": [
            {
                "type": "input_text",
                "text": AGENT_INSTRUCTIONS,
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ],
    }
    first, second = model.calls
    assert first.system_instructions is second.system_instructions is None
    assert first.input[0] == second.input[0] == static_prompt
    assert first.input[1] == _user("something vanilla?")
    assert second.input[-3]["type"] == "function_call"
    assert second.input[-2]["type"] == "function_call_output"
    note = first.input[-1]
    assert second.input[-1] == note
    assert note["role"] == "developer"
    assert note["content"].endswith("The customer's name is Mary.")
    items = await history[str(turn.conversation_id)].get_items()
    assert all(item.get("role") != "developer" for item in items)
