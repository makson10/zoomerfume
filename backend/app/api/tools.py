"""The agent's tool schemas, exactly as the model receives them."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent.tools import build_tools
from app.api.deps import CurrentUser

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolSchema(BaseModel):
    """One tool: its name, the description and the JSON schema of its arguments."""

    name: str
    description: str
    parameters: dict[str, Any]
    # Strict schemas make the model's arguments match ``parameters`` exactly.
    strict: bool


@router.get("/schema")
async def tool_schemas(user: CurrentUser) -> list[ToolSchema]:
    """Return every tool the agent can call, read straight from the tools built for the user."""
    return [
        ToolSchema(
            name=tool.name,
            description=tool.description,
            parameters=tool.params_json_schema,
            strict=tool.strict_json_schema,
        )
        for tool in build_tools(user.id)
    ]
