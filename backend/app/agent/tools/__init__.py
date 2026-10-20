"""The tools Zoomer's agent can call. Each one returns the JSON envelope from ``envelope``."""

from __future__ import annotations

import uuid

from agents import FunctionTool

from app.agent.tools.open_record import open_record
from app.agent.tools.save_note import make_save_note
from app.agent.tools.search_kb import search_kb


def build_tools(user_id: uuid.UUID) -> list[FunctionTool]:
    """Return the agent's tools for one signed-in customer.

    The read tools are shared. ``save_note`` is built for this customer and writes only
    their notes. The schemas are the same for every customer.

    Args:
        user_id: The signed-in customer, from the session cookie.
    """
    return [search_kb, open_record, make_save_note(user_id)]
