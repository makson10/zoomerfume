"""Turns and the tool steps the agent took in them."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.citations import Citations
from app.agent.context import Step, TurnStatus
from app.db.models import ToolStep, Turn


class TurnStore:
    """Reads and writes turns and their tool steps in Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, conversation_id: uuid.UUID) -> uuid.UUID:
        """Insert a running turn and return its id."""
        turn = Turn(id=uuid.uuid4(), conversation_id=conversation_id, status="running")
        self._session.add(turn)
        await self._session.commit()
        return turn.id

    async def finish(
        self, turn_id: uuid.UUID, status: TurnStatus, citations: Citations, steps: list[Step]
    ) -> None:
        """Store how the turn ended, its citations and its tool steps."""
        await self._session.execute(
            update(Turn)
            .where(Turn.id == turn_id)
            .values(status=status, citations=citations.model_dump(), finished_at=func.now())
        )
        self._session.add_all(ToolStep(turn_id=turn_id, **step.model_dump()) for step in steps)
        await self._session.commit()

    async def retrieved_ids(self, conversation_id: uuid.UUID) -> set[str]:
        """Return every record the tools returned in the conversation's turns so far."""
        result = await self._session.scalars(
            select(func.unnest(ToolStep.record_ids))
            .join(Turn, Turn.id == ToolStep.turn_id)
            .where(Turn.conversation_id == conversation_id)
            .distinct()
        )
        return set(result)

    async def for_conversation(self, conversation_id: uuid.UUID) -> list[Turn]:
        """Return the conversation's turns with their tool steps, in two queries."""
        result = await self._session.scalars(
            select(Turn)
            .where(Turn.conversation_id == conversation_id)
            .options(selectinload(Turn.steps))
        )
        return list(result)
