"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """A shop customer, signed in by phone number."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # E.164, e.g. "+14155550123".
    phone: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Conversation(Base):
    """One chat between a user and Zoomer."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The first user message, shortened. Empty until the first message.
    title: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Moves forward with every message, so the newest chats list first.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)


class Message(Base):
    """A single chat message, from the user or from Zoomer."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    # "user" | "assistant"
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Shared by the user message and the reply it produced.
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("turns.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_messages_turn_id", "turn_id"),
    )


class Turn(Base):
    """One customer message and Zoomer's work on it."""

    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    # "running" | "ok" | "max_steps" | "failed"
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # {"valid": [...], "invalid": [...], "missing": bool}. Empty while the turn runs.
    citations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    steps: Mapped[list[ToolStep]] = relationship(order_by="ToolStep.step", lazy="raise")

    __table_args__ = (Index("ix_turns_conversation_id", "conversation_id"),)


class ToolStep(Base):
    """One tool call the agent made during a turn."""

    __tablename__ = "tool_steps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    turn_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False
    )
    # 1, 2, ... in the order the calls finished.
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    args: Mapped[dict] = mapped_column(JSONB, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # The error code of a failed call, e.g. "NOT_FOUND".
    code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # The knowledge base records the call returned.
    record_ids: Mapped[list[str]] = mapped_column(ARRAY(String(8)), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_tool_steps_turn_id", "turn_id"),)


class RateLimit(Base):
    """How many requests one key made in one fixed one-minute window."""

    __tablename__ = "rate_limits"

    # "chat:user:<id>" or "auth:ip:<address>"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class KbRecord(Base):
    """One knowledge base record, as the last ingest read it from the corpus."""

    __tablename__ = "kb_records"

    # "KB-001"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # "product" | "policy" | "company" | "faq" | "news"
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    # The corpus file name, e.g. "KB-001.md".
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    updated: Mapped[date] = mapped_column(Date, nullable=False)
    header: Mapped[dict] = mapped_column(JSONB, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256 of the file. Ingest skips a record whose hash hasn't changed.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
