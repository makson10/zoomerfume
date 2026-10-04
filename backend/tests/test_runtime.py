from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


async def _run_raises(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("model is down")


async def _run_returns_blank(*args: Any, **kwargs: Any) -> Any:
    return SimpleNamespace(final_output="   ")


@pytest.mark.parametrize("fake_run", [_run_raises, _run_returns_blank], ids=["error", "blank"])
async def test_turn_runner_falls_back_when_the_agent_fails(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_run: Any
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Runner, "run", fake_run)
    runner = TurnRunner(settings, async_sessionmaker())

    assert await runner.run("demo", "hi") == FALLBACK_TEXT
