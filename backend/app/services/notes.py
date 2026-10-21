"""The notes Zoomer saves for customers."""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Note

# A note proposed in hardened mode is "pending" until the customer confirms or rejects it.
NoteStatus = Literal["pending", "confirmed", "rejected"]


class NoteStore:
    """Writes and reads customers' notes in Postgres.

    Created once in the app lifespan. Each call opens its own session, so the tool calls
    of one model response, which may run in parallel, never share one.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def add(
        self,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        turn_id: uuid.UUID,
        text: str,
        status: NoteStatus,
    ) -> Note:
        """Save a note for the user, with the conversation and turn it came from."""
        note = Note(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            text=text,
            status=status,
        )
        async with self._sessionmaker() as session:
            session.add(note)
            await session.commit()
        return note

    async def list_for_user(self, user_id: uuid.UUID, limit: int) -> list[Note]:
        """Return the user's newest notes, the newest first. Rejected notes are left out."""
        async with self._sessionmaker() as session:
            result = await session.scalars(
                select(Note)
                .where(Note.user_id == user_id, Note.status != "rejected")
                .order_by(Note.created_at.desc())
                .limit(limit)
            )
            return list(result)

    async def decide(
        self, note_id: uuid.UUID, user_id: uuid.UUID, status: NoteStatus
    ) -> Note | None:
        """Store the customer's decision on one of their pending notes and return the note,
        or ``None`` when the user has no pending note with this id.

        A note is decided once: a second decision, e.g. from another tab, changes nothing.
        """
        async with self._sessionmaker() as session:
            note = await session.scalar(
                update(Note)
                .where(Note.id == note_id, Note.user_id == user_id, Note.status == "pending")
                .values(status=status, decided_at=func.now())
                .returning(Note)
            )
            await session.commit()
            return note

    async def get_for_user(self, note_id: uuid.UUID, user_id: uuid.UUID) -> Note | None:
        """Return the user's note, or ``None`` when the user has no note with this id."""
        async with self._sessionmaker() as session:
            return await session.scalar(
                select(Note).where(Note.id == note_id, Note.user_id == user_id)
            )

    async def proposals(self, conversation_id: uuid.UUID) -> list[Note]:
        """Return the notes in the conversation that waited for the customer, the oldest
        first.

        They are the pending ones and the decided ones. A note saved straight away was never
        decided, so it isn't one of them.
        """
        async with self._sessionmaker() as session:
            result = await session.scalars(
                select(Note)
                .where(
                    Note.conversation_id == conversation_id,
                    or_(Note.status == "pending", Note.decided_at.is_not(None)),
                )
                .order_by(Note.created_at)
            )
            return list(result)
