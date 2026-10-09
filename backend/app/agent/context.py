"""Per-turn run context for the Agents SDK runtime."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass
class TurnContext:
    """Mutable context passed into ``Runner.run(..., context=ctx)``."""

    conversation_id: uuid.UUID
    # The signed-in customer's name, shown to the model in the instructions.
    user_name: str
    # Correlates this turn's message-log rows (user message ↔ reply).
    turn_id: str
    # The exact text the agent saw this turn.
    user_message: str
    # True when the reply was the fallback text rather than a genuine agent answer.
    degraded: bool = False
