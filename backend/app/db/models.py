"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Message(Base):
    """A single chat message, from the user or from Zoomer."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # The client's session id.
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # "user" | "assistant"
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Shared by the user message and the reply it produced.
    turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_turn_id", "turn_id"),
    )
