"""Chat endpoint: one user message in, Zoomer's reply out."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.agent.citations import Citations, check_citations
from app.agent.context import Step
from app.agent.runtime import TurnRunner
from app.api.conversations import require_conversation
from app.api.deps import Conversations, CurrentUser, Turns, get_turn_runner, limit_chat

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    conversation_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    """Zoomer's reply with its checked citations and the tool calls behind it."""

    reply: str
    turn_id: uuid.UUID
    citations: Citations
    steps: list[Step]


@router.post("/chat", dependencies=[Depends(limit_chat)])
async def chat(
    body: ChatRequest,
    user: CurrentUser,
    conversations: Conversations,
    turns: Turns,
    runner: Annotated[TurnRunner, Depends(get_turn_runner)],
) -> ChatResponse:
    """Return Zoomer's reply to one message in one of the user's conversations.

    The turn is stored with its status, its citations and its tool steps. Only an answer
    that finished normally gets its citations checked, because fallback texts cite nothing.

    Raises:
        ApiError: 401 when nobody is signed in, 429 over the rate limit, 404 when the
            conversation isn't the user's.
    """
    conversation = await require_conversation(conversations, body.conversation_id, user)
    await conversations.mark_active(conversation, body.message)
    retrieved_before = await turns.retrieved_ids(conversation.id)
    turn_id = await turns.start(conversation.id)
    result = await runner.run(turn_id, conversation.id, user.name, body.message)
    if result.status == "ok":
        citations = check_citations(result.reply, result.retrieved_ids, retrieved_before)
    else:
        citations = Citations(valid=[], invalid=[], missing=False)
    await turns.finish(turn_id, result.status, citations, result.steps)
    return ChatResponse(
        reply=result.reply, turn_id=turn_id, citations=citations, steps=result.steps
    )
