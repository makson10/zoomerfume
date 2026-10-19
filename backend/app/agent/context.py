"""Per-turn run context for the Agents SDK runtime."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.kb.knowledge_base import KnowledgeBase


class Step(BaseModel):
    """One tool call the agent made during a turn, as the step log shows it."""

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
    # Correlates this turn's message-log rows (user message ↔ reply).
    turn_id: str
    # The exact text the agent saw this turn.
    user_message: str
    kb: KnowledgeBase
    # The tool calls of this turn, in the order they finished.
    steps: list[Step] = field(default_factory=list)
    # True when the reply was the fallback text rather than a genuine agent answer.
    degraded: bool = False
