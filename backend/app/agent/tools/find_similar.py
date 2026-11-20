"""``find_similar``: find perfumes in the shop that smell like a given product."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from agents import RunContextWrapper, function_tool
from pydantic import Field

from app.agent.context import TurnContext
from app.agent.tools.envelope import ErrorCode, ToolError, ToolResult, tool_guard
from app.kb.products import GenderFilter

MAX_K = 5


@function_tool
@tool_guard
async def find_similar(
    ctx: RunContextWrapper[TurnContext],
    product: str,
    k: Annotated[int, Field(ge=1, le=MAX_K)] = 3,
    max_price: int | None = None,
    gender: GenderFilter | None = None,
) -> ToolResult:
    """Find perfumes we sell that smell like one of our products, by the notes and accords they
    share. Returns the closest products, best first, with what each shares with it.

    Args:
        product: The product's name in English as our shop writes it, with the concentration
            spelled out, e.g. "Dior Sauvage Eau de Parfum", or its record id, e.g. "KB-002".
        k: How many similar products to return, from 1 to 5.
        max_price: Only products whose cheapest bottle costs at most this much, in UAH.
        gender: Only perfumes for men or for women. Unisex perfumes are always included.
    """
    if not product.strip():
        raise ToolError(ErrorCode.INVALID_ARGUMENT, "The product is empty.")
    kb = ctx.context.kb
    reference = await kb.find_product(product)
    if reference is None:
        raise ToolError(
            ErrorCode.NOT_FOUND,
            f"We have no product card named {product!r}. If we sell it under another name, "
            "find it with search_kb. Otherwise search the knowledge base for its style.",
        )
    similar = await kb.similar_products(reference.id, k, max_price, gender)
    return ToolResult(
        data={
            "reference": {"record_id": reference.id, "title": reference.title},
            "similar": [asdict(match) for match in similar],
        },
        record_ids=[reference.id, *(match.record_id for match in similar)],
    )
