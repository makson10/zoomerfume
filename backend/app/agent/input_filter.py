"""What each model call sends: the static prompt first and the turn's context note last.

Prompt caching reuses the longest prefix a request shares with an earlier one. The static
prompt opens every request with an explicit cache breakpoint. The volatile note (the time
and the customer's name) goes last and is never stored, so everything before it stays the
same from call to call and from turn to turn.
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
    """Order one model call's input for prompt caching (``RunConfig.call_model_input_filter``).

    The agent's instructions move into the first input item, a developer message with an
    explicit cache breakpoint, because the API's top-level ``instructions`` can't carry
    one. The context note is appended as the last item. The SDK stores only the history,
    so neither of them reaches the session.
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
