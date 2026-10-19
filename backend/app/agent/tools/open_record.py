"""``open_record``: read one knowledge base record in full."""

from __future__ import annotations

import re

from agents import RunContextWrapper, function_tool

from app.agent.context import TurnContext
from app.agent.tools.envelope import ErrorCode, ToolError, ToolResult, tool_guard
from app.kb.corpus import RECORD_ID_PATTERN


@function_tool
@tool_guard
async def open_record(ctx: RunContextWrapper[TurnContext], record_id: str) -> ToolResult:
    """Open one knowledge base record in full: its header (for products: sizes, prices,
    availability) and its whole text. Use it when a search passage is cut off or not enough.

    Args:
        record_id: The record id from a search result, e.g. "KB-042".
    """
    if not re.fullmatch(RECORD_ID_PATTERN, record_id):
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT, f"{record_id!r} is not a record id. Ids look like KB-042."
        )
    record = await ctx.context.kb.get_record(record_id)
    if record is None:
        raise ToolError(ErrorCode.NOT_FOUND, f"There is no record {record_id}.")
    return ToolResult(data={"header": record.header, "body": record.body}, record_ids=[record_id])
