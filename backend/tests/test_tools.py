from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from agents import FunctionTool
from agents.tool_context import ToolContext
from fastapi.testclient import TestClient

from app.agent.context import TurnContext
from app.agent.tools import open_record, search_kb
from app.db.models import KbRecord, User
from tests.fakes import FakeKnowledgeBase, make_hit


@pytest.fixture
def ctx(fake_kb: FakeKnowledgeBase) -> TurnContext:
    return TurnContext(
        conversation_id=uuid.uuid4(),
        user_name="Mary",
        turn_id="turn-1",
        user_message="hi",
        kb=fake_kb,
    )


async def call_tool(tool: FunctionTool, ctx: TurnContext, **args: Any) -> dict[str, Any]:
    """Invoke a tool the way the agent loop does: JSON arguments in, JSON envelope out."""
    arguments = json.dumps(args)
    tool_context = ToolContext(
        context=ctx, tool_name=tool.name, tool_call_id="call-1", tool_arguments=arguments
    )
    return json.loads(await tool.on_invoke_tool(tool_context, arguments))


async def test_search_kb_returns_hits_and_records_the_step(
    ctx: TurnContext, fake_kb: FakeKnowledgeBase
) -> None:
    fake_kb.hits = [make_hit("KB-012", 0.91234), make_hit("KB-012"), make_hit("KB-031")]

    result = await call_tool(
        search_kb, ctx, query="vanilla", k=50, record_type="product", max_price=3000
    )

    assert result["success"] is True
    hits = result["data"]["hits"]
    assert [hit["record_id"] for hit in hits] == ["KB-012", "KB-012", "KB-031"]
    assert hits[0]["score"] == 0.912
    assert fake_kb.searches == [("vanilla", 8, "product", 3000)]
    [step] = ctx.steps
    assert step.tool == "search_kb"
    assert step.args == {"query": "vanilla", "k": 50, "record_type": "product", "max_price": 3000}
    assert step.success is True
    assert step.record_ids == ["KB-012", "KB-031"]


async def test_open_record_returns_the_full_record(
    ctx: TurnContext, fake_kb: FakeKnowledgeBase
) -> None:
    fake_kb.records["KB-012"] = KbRecord(
        id="KB-012", header={"id": "KB-012", "title": "Vanilla Musk"}, body="## Overview\nSoft."
    )

    result = await call_tool(open_record, ctx, record_id="KB-012")

    assert result == {
        "success": True,
        "data": {"header": {"id": "KB-012", "title": "Vanilla Musk"}, "body": "## Overview\nSoft."},
    }
    assert ctx.steps[0].record_ids == ["KB-012"]


@pytest.mark.parametrize(
    ("record_id", "code"),
    [("KB-12", "INVALID_ARGUMENT"), ("KB-999", "NOT_FOUND")],
    ids=["bad-format", "unknown-id"],
)
async def test_open_record_fails_with_an_error_code(
    ctx: TurnContext, record_id: str, code: str
) -> None:
    result = await call_tool(open_record, ctx, record_id=record_id)

    assert result["success"] is False
    assert result["code"] == code
    assert record_id in result["message"]
    assert (ctx.steps[0].success, ctx.steps[0].code) == (False, code)


async def test_tool_exceptions_become_an_upstream_error(
    ctx: TurnContext, fake_kb: FakeKnowledgeBase
) -> None:
    fake_kb.error = RuntimeError("connection refused: qdrant:6333")

    result = await call_tool(search_kb, ctx, query="vanilla")

    assert result["success"] is False
    assert result["code"] == "UPSTREAM_ERROR"
    assert "qdrant:6333" not in result["message"]
    assert (ctx.steps[0].success, ctx.steps[0].record_ids) == (False, [])


def test_schema_endpoint_lists_both_tools_with_strict_schemas(
    client: TestClient, user: User
) -> None:
    schemas = client.get("/api/tools/schema").json()

    assert [schema["name"] for schema in schemas] == ["search_kb", "open_record"]
    for schema in schemas:
        assert schema["strict"] is True
        assert schema["parameters"]["additionalProperties"] is False
    assert list(schemas[1]["parameters"]["properties"]) == ["record_id"]
