"""``search_kb``: search the shop's knowledge base by meaning."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from agents import RunContextWrapper, function_tool
from pydantic import Field

from app.agent.context import TurnContext
from app.agent.tools.envelope import ErrorCode, ToolError, ToolResult, tool_guard
from app.kb.corpus import RecordType

MAX_K = 8


@function_tool
@tool_guard
async def search_kb(
    ctx: RunContextWrapper[TurnContext],
    query: str,
    k: Annotated[int, Field(ge=1, le=MAX_K)] = 5,
    record_type: RecordType | None = None,
    max_price: int | None = None,
) -> ToolResult:
    """Search Zoomerfume's knowledge base: products we sell, prices, delivery, payment, returns,
    loyalty points, services, company facts and news. Returns the closest passages, best first.

    Args:
        query: What to look for, in English, e.g. "warm vanilla perfume for winter evenings".
        k: How many passages to return, from 1 to 8.
        record_type: Only search records of this type, e.g. "product" for perfumes we sell.
        max_price: Only products whose cheapest bottle costs at most this much, in UAH.
    """
    if not query.strip():
        raise ToolError(ErrorCode.INVALID_ARGUMENT, "The query is empty.")
    hits = await ctx.context.kb.search(query, k, record_type, max_price)
    return ToolResult(
        data={"hits": [{**asdict(hit), "score": round(hit.score, 3)} for hit in hits]},
        record_ids=list(dict.fromkeys(hit.record_id for hit in hits)),
    )
