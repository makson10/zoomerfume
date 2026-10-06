"""Test doubles for the app's boundaries."""

from __future__ import annotations

import uuid

from app.db.models import User


class FakeTurnRunner:
    """Stands in for ``TurnRunner``: records each call and returns a canned reply."""

    reply = "fake reply"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def run(self, session_id: str, text: str) -> str:
        self.calls.append((session_id, text))
        return self.reply


class FakeUserStore:
    """Stands in for ``UserStore`` with users kept in memory."""

    def __init__(self) -> None:
        self.users: dict[uuid.UUID, User] = {}

    def add(self, phone: str, name: str) -> User:
        user = User(id=uuid.uuid4(), phone=phone, name=name)
        self.users[user.id] = user
        return user

    async def get(self, user_id: uuid.UUID) -> User | None:
        return self.users.get(user_id)

    async def get_by_phone(self, phone: str) -> User | None:
        return next((user for user in self.users.values() if user.phone == phone), None)

    async def get_or_create(self, phone: str, name: str) -> User:
        return await self.get_by_phone(phone) or self.add(phone, name)
