"""Durable message log: one row per user message and one per Zoomer reply.

Side-written after the reply is produced. Guarded so a database hiccup never
delays or breaks a turn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.guard import pg_guard
from app.db.models import Message

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agent.context import TurnContext


@pg_guard
async def record_turn_messages(
    sessionmaker: async_sessionmaker[AsyncSession], ctx: TurnContext, reply: str
) -> None:
    """Persist the user message + Zoomer's reply for a turn."""
    rows = [
        Message(
            conversation_id=ctx.conversation_id,
            role="user",
            content=ctx.user_message,
            turn_id=ctx.turn_id,
        ),
        Message(
            conversation_id=ctx.conversation_id,
            role="assistant",
            content=reply,
            turn_id=ctx.turn_id,
            meta={"degraded": ctx.degraded},
        ),
    ]
    async with sessionmaker() as session:
        session.add_all(rows)
        await session.commit()
