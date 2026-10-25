"""The part of a conversation's history the model gets in each turn."""

from __future__ import annotations

import logging

from agents.items import TResponseInputItem

logger = logging.getLogger(__name__)


def window_history(
    history: list[TResponseInputItem],
    new_items: list[TResponseInputItem],
    *,
    turns: int,
) -> list[TResponseInputItem]:
    """Return the last ``turns`` turns of the history, then this turn's items.

    It is the run's ``session_input_callback``, so only the model input gets shorter and the
    stored history stays whole. The cut falls where a turn starts, so a tool call always
    keeps its output. ``turns <= 0`` turns the window off.
    """
    if turns <= 0:
        return history + new_items
    starts = _turn_starts(history)
    if len(starts) <= turns:
        return history + new_items
    cut = starts[-turns]
    logger.debug(
        "history windowed | items %d -> %d (last %d turns)", len(history), len(history) - cut, turns
    )
    return history[cut:] + new_items


def _turn_starts(history: list[TResponseInputItem]) -> list[int]:
    """Return the positions where a turn starts: the first of one or more input messages."""
    starts: list[int] = []
    previous_is_input = False
    for index, item in enumerate(history):
        is_input = _is_input_message(item)
        if is_input and not previous_is_input:
            starts.append(index)
        previous_is_input = is_input
    return starts


def _is_input_message(item: TResponseInputItem) -> bool:
    """True for a ``user`` or ``developer`` message. Tool items have a ``type`` and no role."""
    return (
        isinstance(item, dict)
        and item.get("type") in (None, "message")
        and item.get("role") in ("user", "developer")
    )
