"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all tables."""


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
    # The first user message, shortened.
    title: Mapped[str] = mapped_column(String(80), nullable=False)
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
    # "chat" | "command": a chat command such as /cost and its reply, which run no turn.
    kind: Mapped[str] = mapped_column(String(16), server_default="chat", nullable=False)
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
    # "running" | "ok" | "max_steps" | "cancelled" | "failed"
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # {"valid": [...], "invalid": [...], "missing": bool}. Empty while the turn runs.
    citations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # The prompt-injection defenses the turn ran with: "hardened", "vulnerable" or the
    # defenses that were on, e.g. "wrap+confirm".
    security_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    steps: Mapped[list[ToolStep]] = relationship(order_by="ToolStep.step", lazy="raise")

    __table_args__ = (
        Index("ix_turns_conversation_id", "conversation_id"),
        # One running turn per conversation: a second message waits for the first reply.
        Index(
            "ux_turns_one_running",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )


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


class LlmCall(Base):
    """One model call and what it cost: a chat call of a turn, or an embeddings call."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Empty for ingest, which runs outside any turn.
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("turns.id", ondelete="SET NULL"), nullable=True
    )
    # "chat" | "embedding"
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    # All input tokens, the cached and cache-write ones included.
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 9), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_llm_calls_turn_id", "turn_id"),)


class Note(Base):
    """A note Zoomer saved for a customer, e.g. a wishlist item."""

    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Where the note was saved.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("turns.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    # "pending" while it waits for the customer, then "confirmed" or "rejected". A note
    # saved straight away is "confirmed".
    status: Mapped[str] = mapped_column(String(16), server_default="confirmed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # When the customer confirmed or rejected a pending note. Empty for a note saved
    # straight away.
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_notes_user_created", "user_id", "created_at"),
        Index("ix_notes_conversation_id", "conversation_id"),
    )


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
