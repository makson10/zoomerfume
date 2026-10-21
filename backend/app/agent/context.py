"""Per-turn run context for the Agents SDK runtime."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.core.security import SecurityPolicy
    from app.kb.knowledge_base import KnowledgeBase
    from app.services.notes import NoteStore
    from app.services.usage import CallUsage

# How a turn ended: an answer, the polite answer at the step limit, stopped by the
# customer, or the fallback text.
TurnStatus = Literal["ok", "max_steps", "cancelled", "failed"]


class Step(BaseModel):
    """One tool call the agent made during a turn, as the step log shows it."""

    model_config = ConfigDict(from_attributes=True)

    step: int
    tool: str
    args: dict[str, Any]
    success: bool
    code: str | None
    record_ids: list[str]
    duration_ms: int


class PendingNote(BaseModel):
    """A note ``save_note`` proposed. It waits for the customer to confirm or reject it."""

    note_id: uuid.UUID
    text: str


@dataclass
class TurnContext:
    """Mutable context passed into ``Runner.run(..., context=ctx)``.

    The tools reach the knowledge base and the notes through it and record their calls in
    it. It holds no user id: ``save_note`` writes for the customer it was built for (see
    ``build_tools``).
    """

    conversation_id: uuid.UUID
    # The signed-in customer's name, shown to the model in the context note.
    user_name: str
    # The turn's row in ``turns``, shared by its message-log rows and tool steps.
    turn_id: uuid.UUID
    # The exact text the agent saw this turn.
    user_message: str
    kb: KnowledgeBase
    notes: NoteStore
    # The prompt-injection defenses the tools apply.
    security: SecurityPolicy
    # The time in the context note, the same for every model call of the turn.
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # The tool calls of this turn, in the order they finished.
    steps: list[Step] = field(default_factory=list)
    # The model calls of this turn: the agent's chat calls and the searches' embeddings.
    calls: list[CallUsage] = field(default_factory=list)
    # The notes this turn proposed, in the order they were proposed.
    pending_notes: list[PendingNote] = field(default_factory=list)
    status: TurnStatus = "ok"

    @property
    def retrieved_ids(self) -> set[str]:
        """The records this turn's tools returned."""
        return {record_id for step in self.steps for record_id in step.record_ids}
