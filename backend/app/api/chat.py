"""Chat endpoint: one user message in, Zoomer's reply out."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.agent.runtime import run_turn

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat")
async def chat(body: ChatRequest) -> ChatResponse:
    reply = await run_turn(body.session_id, body.message)
    return ChatResponse(reply=reply)
