"""Test doubles for the app's boundaries."""

from __future__ import annotations

import uuid

from app.db.models import Conversation, Message, User
from app.services.conversations import conversation_title


class FakeTurnRunner:
    """Stands in for ``TurnRunner``: records each call and returns a canned reply."""

    reply = "fake reply"

    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, str, str]] = []

    async def run(self, conversation_id: uuid.UUID, user_name: str, text: str) -> str:
        self.calls.append((conversation_id, user_name, text))
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


class FakeConversationStore:
    """Stands in for ``ConversationStore``. The list is kept most recently active first."""

    def __init__(self) -> None:
        self.conversations: list[Conversation] = []
        self.transcripts: dict[uuid.UUID, list[Message]] = {}

    async def list_for_user(self, user_id: uuid.UUID) -> list[Conversation]:
        return [c for c in self.conversations if c.user_id == user_id]

    def add(self, user_id: uuid.UUID) -> Conversation:
        conversation = Conversation(id=uuid.uuid4(), user_id=user_id, title=None)
        self.conversations.insert(0, conversation)
        return conversation

    async def create(self, user_id: uuid.UUID) -> Conversation:
        return self.add(user_id)

    async def get_for_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        return next(
            (c for c in self.conversations if c.id == conversation_id and c.user_id == user_id),
            None,
        )

    async def messages(self, conversation_id: uuid.UUID) -> list[Message]:
        return self.transcripts.get(conversation_id, [])

    async def mark_active(self, conversation: Conversation, message: str) -> None:
        if conversation.title is None:
            conversation.title = conversation_title(message)
        self.conversations.remove(conversation)
        self.conversations.insert(0, conversation)
