"""Test doubles for the app's boundaries."""

from __future__ import annotations


class FakeTurnRunner:
    """Stands in for ``TurnRunner``: records each call and returns a canned reply."""

    reply = "fake reply"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def run(self, session_id: str, text: str) -> str:
        self.calls.append((session_id, text))
        return self.reply
