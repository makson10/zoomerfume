"""The message log: one row per customer message and one per Zoomer reply."""

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
    """Write the turn's customer message and Zoomer's reply. Fail-open, like every log write.

    A turn stopped before Zoomer wrote anything has no reply row.
    """
    async with sessionmaker() as session:
        session.add_all(
            Message(
                conversation_id=ctx.conversation_id, role=role, content=content, turn_id=ctx.turn_id
            )
            for role, content in [("user", ctx.user_message), ("assistant", reply)]
            if content
        )
        await session.commit()
