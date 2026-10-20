"""The notes Zoomer saves for customers."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Note


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
    ) -> Note:
        """Save a confirmed note for the user, with the conversation and turn it came from."""
        note = Note(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            text=text,
            status="confirmed",
        )
        async with self._sessionmaker() as session:
            session.add(note)
            await session.commit()
        return note

    async def list_for_user(self, user_id: uuid.UUID, limit: int) -> list[Note]:
        """Return the user's newest notes, the newest first."""
        async with self._sessionmaker() as session:
            result = await session.scalars(
                select(Note)
                .where(Note.user_id == user_id)
                .order_by(Note.created_at.desc())
                .limit(limit)
            )
            return list(result)
