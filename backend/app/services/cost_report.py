"""The ``/cost`` report: what a conversation's turns cost, as a Markdown table."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.agent.input_filter import SHOP_TIMEZONE
from app.db.models import Turn
from app.services.usage import TurnUsage

COST_COMMAND = "/cost"

NOTHING_YET = "Nothing to count yet: Zoomer hasn't answered in this chat."
HEADER = (
    "| # | Time | Calls | Input | Cached | Cache write | Output | Cost |\n"
    "|---:|---|---:|---:|---:|---:|---:|---:|"
)
FOOTNOTE = (
    "Turn 1 starts with a cache write: each chat has its own cache key, so its first call "
    "has nothing to read and writes the prompt and the message to the cache instead. Every "
    "later call, in turn 1 or after it, reads what came before at a tenth of the input "
    "price. Calls and tokens are the chat model's; the cost also covers the search "
    "embeddings."
)


def _row(label: str, time: str, usage: TurnUsage) -> str:
    return (
        f"| {label} | {time} | {usage.calls} | {usage.input_tokens:,} | {usage.cached_tokens:,} "
        f"| {usage.cache_write_tokens:,} | {usage.output_tokens:,} | {_usd(usage.cost_usd)} |"
    )


def _usd(amount: Decimal) -> str:
    return f"${amount:.6f}"


def cost_report(turns: Sequence[Turn]) -> str:
    """Return the conversation's cost per turn and in total, with the share read from cache.

    Args:
        turns: The conversation's turns, oldest first, with their model calls loaded. Turns
            that are still running are left out, because their calls aren't stored yet.
    """
    finished = [turn for turn in turns if turn.status != "running"]
    if not finished:
        return NOTHING_YET
    rows = []
    for number, turn in enumerate(finished, start=1):
        started = turn.started_at.astimezone(SHOP_TIMEZONE)
        rows.append(_row(str(number), f"{started:%H:%M}", TurnUsage.of(turn.calls)))
    total = TurnUsage.of([call for turn in finished for call in turn.calls])
    hit_rate = total.cached_tokens / total.input_tokens if total.input_tokens else 0
    return "\n".join(
        [
            "**What this chat cost** (times in Kyiv)",
            "",
            HEADER,
            *rows,
            _row("**Total**", "", total),
            "",
            f"{hit_rate:.0%} of the input tokens were read from the cache.",
            "",
            FOOTNOTE,
        ]
    )
