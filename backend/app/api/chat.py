"""Chat endpoint: one user message in, Zoomer's reply out."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.agent.runtime import TurnRunner
from app.api.deps import get_turn_runner

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat")
async def chat(
    body: ChatRequest, runner: Annotated[TurnRunner, Depends(get_turn_runner)]
) -> ChatResponse:
    """Return Zoomer's reply to one user message."""
    reply = await runner.run(body.session_id, body.message)
    return ChatResponse(reply=reply)
