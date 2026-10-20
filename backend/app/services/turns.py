"""Turns, the tool steps the agent took in them and their model calls."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.citations import Citations
from app.agent.context import Step, TurnStatus
from app.db.models import ToolStep, Turn
from app.services.usage import CallUsage

# A turn still running after this long was left behind by a server that stopped mid-turn.
STALE_TURN_AFTER = timedelta(minutes=2)
# The partial index's predicate as literal SQL. Postgres matches ON CONFLICT to the index
# by its predicate, and a bound parameter stops matching once the statement is cached.
RUNNING_TURN_INDEX_WHERE = text("status = 'running'")


class TurnStore:
    """Reads and writes turns, their tool steps and their model calls in Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, conversation_id: uuid.UUID) -> uuid.UUID | None:
        """Insert a running turn and return its id, or ``None`` while another turn runs.

        A partial unique index allows one running turn per conversation. A running turn
        older than :data:`STALE_TURN_AFTER` is marked ``failed`` first, so a server that
        stopped mid-turn can't block the conversation.
        """
        await self._session.execute(
            update(Turn)
            .where(
                Turn.conversation_id == conversation_id,
                Turn.status == "running",
                Turn.started_at < func.now() - STALE_TURN_AFTER,
            )
            .values(status="failed", finished_at=func.now())
        )
        turn_id = await self._session.scalar(
            insert(Turn)
            .values(id=uuid.uuid4(), conversation_id=conversation_id, status="running")
            .on_conflict_do_nothing(
                index_elements=[Turn.conversation_id], index_where=RUNNING_TURN_INDEX_WHERE
            )
            .returning(Turn.id)
        )
        await self._session.commit()
        return turn_id

    async def finish(
        self,
        turn_id: uuid.UUID,
        status: TurnStatus,
        citations: Citations,
        steps: list[Step],
        calls: list[CallUsage],
    ) -> None:
        """Store how the turn ended, its citations, its tool steps and its model calls."""
        await self._session.execute(
            update(Turn)
            .where(Turn.id == turn_id)
            .values(status=status, citations=citations.model_dump(), finished_at=func.now())
        )
        self._session.add_all(ToolStep(turn_id=turn_id, **step.model_dump()) for step in steps)
        self._session.add_all(call.as_row(turn_id) for call in calls)
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
        """Return the conversation's turns with their tool steps and model calls, in three
        queries."""
        result = await self._session.scalars(
            select(Turn)
            .where(Turn.conversation_id == conversation_id)
            .options(selectinload(Turn.steps), selectinload(Turn.calls))
        )
        return list(result)
