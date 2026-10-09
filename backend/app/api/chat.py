"""Chat endpoint: one user message in, Zoomer's reply out."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.agent.runtime import TurnRunner
from app.api.conversations import require_conversation
from app.api.deps import Conversations, CurrentUser, get_turn_runner, limit_chat

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    conversation_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", dependencies=[Depends(limit_chat)])
async def chat(
    body: ChatRequest,
    user: CurrentUser,
    conversations: Conversations,
    runner: Annotated[TurnRunner, Depends(get_turn_runner)],
) -> ChatResponse:
    """Return Zoomer's reply to one message in one of the user's conversations.

    Raises:
        ApiError: 401 when nobody is signed in, 429 over the rate limit, 404 when the
            conversation isn't the user's.
    """
    conversation = await require_conversation(conversations, body.conversation_id, user)
    await conversations.mark_active(conversation, body.message)
    reply = await runner.run(conversation.id, user.name, body.message)
    return ChatResponse(reply=reply)
