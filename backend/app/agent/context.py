"""Per-turn run context for the Agents SDK runtime."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.kb.knowledge_base import KnowledgeBase

# How a turn ended: an answer, the polite answer at the step limit, or the fallback text.
TurnStatus = Literal["ok", "max_steps", "failed"]


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


@dataclass
class TurnContext:
    """Mutable context passed into ``Runner.run(..., context=ctx)``.

    The tools read the knowledge base through it and record their calls in it.
    """

    conversation_id: uuid.UUID
    # The signed-in customer's name, shown to the model in the instructions.
    user_name: str
    # The turn's row in ``turns``, shared by its message-log rows and tool steps.
    turn_id: uuid.UUID
    # The exact text the agent saw this turn.
    user_message: str
    kb: KnowledgeBase
    # The tool calls of this turn, in the order they finished.
    steps: list[Step] = field(default_factory=list)
    status: TurnStatus = "ok"
