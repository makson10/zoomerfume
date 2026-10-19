"""The tools Zoomer's agent can call. Each one returns the JSON envelope from ``envelope``."""

from app.agent.tools.open_record import open_record
from app.agent.tools.search_kb import search_kb

TOOLS = [search_kb, open_record]
