"""A user's conversations with Zoomer and their transcripts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Conversation, Message

TITLE_MAX_LENGTH = 60


def conversation_title(message: str) -> str:
    """Shorten the first user message into a one-line conversation title."""
    title = " ".join(message.split())
    if len(title) <= TITLE_MAX_LENGTH:
        return title
    return title[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


class ConversationStore:
    """Reads and writes conversations and reads their message log in Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[Conversation]:
        """Return the user's conversations, the most recently active first."""
        result = await self._session.scalars(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result)

    async def create(self, user_id: uuid.UUID) -> Conversation:
        conversation = Conversation(id=uuid.uuid4(), user_id=user_id, title=None)
        self._session.add(conversation)
        await self._session.commit()
        return conversation

    async def get_for_user(
        self, conversation_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        """Return the conversation if it exists and belongs to the user."""
        return await self._session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )

    async def messages(self, conversation_id: uuid.UUID) -> list[Message]:
        """Return the conversation's logged messages, oldest first."""
        result = await self._session.scalars(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id)
        )
        return list(result)

    async def mark_active(self, conversation: Conversation, message: str) -> None:
        """Move the conversation to the top of the list, titled after its first message."""
        if conversation.title is None:
            conversation.title = conversation_title(message)
        conversation.updated_at = datetime.now(UTC)
        await self._session.commit()
