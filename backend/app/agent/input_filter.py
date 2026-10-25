"""What each model call sends: the static prompt first and the turn's context note last.

Only the note changes from turn to turn, so everything before it stays a cacheable prefix.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.run_config import CallModelData, ModelInputData

from app.agent.context import TurnContext

# The shop's rules (cutoffs, support hours) are in Kyiv time.
SHOP_TIMEZONE = ZoneInfo("Europe/Kyiv")


def context_note(now: datetime, user_name: str) -> str:
    """Return the developer note with the shop's local time and the customer's name."""
    local = now.astimezone(SHOP_TIMEZONE)
    return (
        f"Now: {local:%A}, {local.day} {local:%B %Y, %H:%M} Kyiv time. "
        f"The customer's name is {user_name}."
    )


def cacheable_input(data: CallModelData[TurnContext]) -> ModelInputData:
    """Put the instructions first, with a cache breakpoint, and the context note last.

    The API's top-level ``instructions`` can't carry a breakpoint, so they move into the
    input. Neither item reaches the stored history.
    """
    ctx = data.context
    static_prompt = {
        "role": "developer",
        "content": [
            {
                "type": "input_text",
                "text": data.model_data.instructions,
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ],
    }
    note = {"role": "developer", "content": context_note(ctx.started_at, ctx.user_name)}
    return ModelInputData(input=[static_prompt, *data.model_data.input, note], instructions=None)
