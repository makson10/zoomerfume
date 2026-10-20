"""Test doubles for the app's boundaries."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from app.agent.citations import Citations
from app.agent.context import Step, TurnStatus
from app.agent.runtime import NewTurn, TurnResult, TurnStart
from app.agent.streaming import Token, ToolCall, TurnEvent
from app.db.models import Conversation, KbRecord, Message, Note, ToolStep, Turn, User
from app.kb.search import Hit
from app.services.conversations import conversation_title
from app.services.usage import CallUsage, TurnUsage


class FakeTurnRunner:
    """Stands in for ``TurnRunner``: records each turn and streams a canned reply, status,
    steps and model calls, then stores the turn like the real runner."""

    reply = "fake reply"
    status: TurnStatus = "ok"

    def __init__(self) -> None:
        self.calls: list[NewTurn] = []
        self.steps: list[Step] = []
        self.citations = Citations()
        self.model_calls = [CallUsage("chat", "gpt-6-luna", 2000, 1800, 100, 50)]

    async def stream(
        self, turn: NewTurn, turns: FakeTurnStore
    ) -> AsyncIterator[TurnStart | TurnEvent | TurnResult]:
        self.calls.append(turn)
        yield TurnStart(conversation_id=turn.conversation_id, turn_id=turn.id)
        for step in self.steps:
            yield ToolCall(tool=step.tool, args=step.args)
            yield step
        yield Token(text=self.reply)
        await turns.finish(turn.id, self.status, self.citations, self.steps, self.model_calls)
        yield TurnResult(
            conversation_id=turn.conversation_id,
            turn_id=turn.id,
            reply=self.reply,
            status=self.status,
            citations=self.citations,
            steps=self.steps,
            usage=TurnUsage.of(self.model_calls),
        )


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

    def add(self, user_id: uuid.UUID, title: str = "hi") -> Conversation:
        conversation = Conversation(id=uuid.uuid4(), user_id=user_id, title=title)
        self.conversations.insert(0, conversation)
        return conversation

    async def create(self, user_id: uuid.UUID, first_message: str) -> Conversation:
        return self.add(user_id, conversation_title(first_message))

    async def get_for_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        return next(
            (c for c in self.conversations if c.id == conversation_id and c.user_id == user_id),
            None,
        )

    async def messages(self, conversation_id: uuid.UUID) -> list[Message]:
        return self.transcripts.get(conversation_id, [])

    async def mark_active(self, conversation: Conversation) -> None:
        self.conversations.remove(conversation)
        self.conversations.insert(0, conversation)


class FakeRateLimiter:
    """Stands in for ``RateLimiter``: records each hit and allows them all until
    ``retry_after`` is set."""

    def __init__(self) -> None:
        self.hits: list[tuple[str, int]] = []
        self.retry_after: int | None = None

    async def hit(self, key: str, limit: int) -> int | None:
        self.hits.append((key, limit))
        return self.retry_after


def make_hit(record_id: str, score: float = 0.8) -> Hit:
    return Hit(
        record_id=record_id,
        title=f"Record {record_id}",
        type="product",
        chunk_index=0,
        section=f"Record {record_id} › Overview",
        updated="2026-09-01",
        score=score,
        text=f"Text of {record_id}.",
        price=2500,
    )


class FakeKnowledgeBase:
    """Stands in for ``KnowledgeBase``: canned hits and records. Records every search, and
    raises ``error`` when it is set."""

    def __init__(self) -> None:
        self.hits: list[Hit] = []
        self.records: dict[str, KbRecord] = {}
        self.searches: list[tuple[str, int, str | None, int | None]] = []
        self.error: Exception | None = None

    async def search(
        self, query: str, k: int, record_type: str | None, max_price: int | None
    ) -> tuple[list[Hit], CallUsage]:
        self.searches.append((query, k, record_type, max_price))
        if self.error is not None:
            raise self.error
        return self.hits[:k], CallUsage("embedding", "text-embedding-3-small", 8)

    async def get_record(self, record_id: str) -> KbRecord | None:
        return self.records.get(record_id)


class FakeNoteStore:
    """Stands in for ``NoteStore`` with notes kept in memory, the newest last."""

    def __init__(self) -> None:
        self.notes: list[Note] = []

    async def add(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID, turn_id: uuid.UUID, text: str
    ) -> Note:
        note = Note(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            text=text,
            status="confirmed",
            created_at=datetime.now(UTC),
        )
        self.notes.append(note)
        return note

    async def list_for_user(self, user_id: uuid.UUID, limit: int) -> list[Note]:
        return [note for note in reversed(self.notes) if note.user_id == user_id][:limit]


def make_step(record_ids: list[str]) -> Step:
    return Step(
        step=1,
        tool="search_kb",
        args={"query": "vanilla"},
        success=True,
        code=None,
        record_ids=record_ids,
        duration_ms=12,
    )


class FakeTurnStore:
    """Stands in for ``TurnStore`` with turns, their steps and model calls kept in memory.
    Like the real store, it starts no turn while another one in the conversation is
    running."""

    def __init__(self) -> None:
        self.turns: dict[uuid.UUID, Turn] = {}

    def add(
        self,
        conversation_id: uuid.UUID,
        citations: Citations | None,
        steps: list[Step],
        status: str = "ok",
        calls: list[CallUsage] | None = None,
    ) -> Turn:
        turn = Turn(id=uuid.uuid4(), conversation_id=conversation_id, status="running")
        self.turns[turn.id] = turn
        self._finish(turn, status, citations, steps, calls or [])
        return turn

    def _finish(
        self,
        turn: Turn,
        status: str,
        citations: Citations | None,
        steps: list[Step],
        calls: list[CallUsage],
    ) -> None:
        turn.status = status
        turn.citations = citations.model_dump() if citations else None
        turn.steps = [ToolStep(turn_id=turn.id, **step.model_dump()) for step in steps]
        turn.calls = [call.as_row(turn.id) for call in calls]

    async def start(self, conversation_id: uuid.UUID) -> uuid.UUID | None:
        if any(
            turn.conversation_id == conversation_id and turn.status == "running"
            for turn in self.turns.values()
        ):
            return None
        turn = Turn(id=uuid.uuid4(), conversation_id=conversation_id, status="running")
        self.turns[turn.id] = turn
        return turn.id

    async def finish(
        self,
        turn_id: uuid.UUID,
        status: TurnStatus,
        citations: Citations,
        steps: list[Step],
        calls: list[CallUsage],
    ) -> None:
        self._finish(self.turns[turn_id], status, citations, steps, calls)

    async def retrieved_ids(self, conversation_id: uuid.UUID) -> set[str]:
        return {
            record_id
            for turn in self.turns.values()
            if turn.conversation_id == conversation_id
            for step in turn.steps
            for record_id in step.record_ids
        }

    async def for_conversation(self, conversation_id: uuid.UUID) -> list[Turn]:
        return [turn for turn in self.turns.values() if turn.conversation_id == conversation_id]
