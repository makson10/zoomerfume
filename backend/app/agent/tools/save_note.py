"""``save_note``: save a note for the signed-in customer."""

from __future__ import annotations

import uuid

from agents import FunctionTool, RunContextWrapper, function_tool

from app.agent.context import TurnContext
from app.agent.tools.envelope import ErrorCode, ToolError, ToolResult, tool_guard

MAX_NOTE_LENGTH = 500


def make_save_note(user_id: uuid.UUID) -> FunctionTool:
    """Build ``save_note`` for one customer.

    The tool closes over ``user_id``, so its notes always go to that customer. The id is
    not a parameter, so the model never sees it and has no way to pass another one.

    Args:
        user_id: The signed-in customer, from the session cookie.
    """

    @function_tool
    @tool_guard
    async def save_note(ctx: RunContextWrapper[TurnContext], text: str) -> ToolResult:
        """Save a short note to the customer's personal notes: a wishlist item, a reminder or
        anything else they ask you to remember. Use it only when the customer explicitly asks
        you to save, add or remember something.

        Args:
            text: The note, short and specific, e.g. "Wishlist: Jazz Club, 100 ml". At most 500
                characters.
        """
        note_text = text.strip()
        if not 1 <= len(note_text) <= MAX_NOTE_LENGTH:
            raise ToolError(
                ErrorCode.INVALID_ARGUMENT,
                f"A note needs 1 to {MAX_NOTE_LENGTH} characters, this one has {len(note_text)}.",
            )
        turn = ctx.context
        note = await turn.notes.add(user_id, turn.conversation_id, turn.turn_id, note_text)
        return ToolResult(data={"note_id": str(note.id), "status": note.status})

    return save_note
