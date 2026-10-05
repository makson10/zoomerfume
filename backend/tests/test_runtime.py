from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from agents import Runner
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agent.runtime import FALLBACK_TEXT, TurnRunner, window_history
from app.core.config import Settings


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


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (SimpleNamespace(final_output=" try a vanilla musk "), "try a vanilla musk"),
        (SimpleNamespace(final_output="   "), FALLBACK_TEXT),
        (RuntimeError("model is down"), FALLBACK_TEXT),
    ],
    ids=["reply", "blank", "error"],
)
async def test_turn_runner_returns_the_reply_or_the_fallback(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    outcome: Any,
    expected: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    fake_run = AsyncMock(side_effect=[outcome])
    monkeypatch.setattr(Runner, "run", fake_run)
    runner = TurnRunner(settings, async_sessionmaker())

    assert await runner.run("demo", "hi") == expected
    fake_run.assert_awaited_once()
