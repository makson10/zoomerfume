"""Chat endpoint: one user message in, Zoomer's reply out."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from app.agent.citations import Citations, check_citations
from app.agent.context import Step
from app.agent.runtime import TurnRunner
from app.api.conversations import require_conversation
from app.api.deps import Conversations, CurrentUser, Turns, get_turn_runner, limit_chat
from app.api.errors import ApiError

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


@dataclass(frozen=True)
class NewTurn:
    """A running turn in one of the user's conversations, waiting for the agent."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    user_name: str
    message: str
    # The records the tools returned in the conversation's earlier turns.
    retrieved_before: set[str]


async def start_turn(
    body: ChatRequest, user: CurrentUser, conversations: Conversations, turns: Turns
) -> NewTurn:
    """Start a turn for the message in one of the user's conversations.

    Raises:
        ApiError: 404 when the conversation isn't the user's, 409 while Zoomer is still
            answering another message in it.
    """
    conversation = await require_conversation(conversations, body.conversation_id, user)
    turn_id = await turns.start(conversation.id)
    if turn_id is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "REPLY_IN_PROGRESS",
            "I'm still answering your last message in this chat. "
            "Wait for my reply or stop it, then send this one again.",
        )
    await conversations.mark_active(conversation, body.message)
    retrieved_before = await turns.retrieved_ids(conversation.id)
    return NewTurn(turn_id, conversation.id, user.name, body.message, retrieved_before)


@router.post("/chat", dependencies=[Depends(limit_chat)])
async def chat(
    turn: Annotated[NewTurn, Depends(start_turn)],
    turns: Turns,
    runner: Annotated[TurnRunner, Depends(get_turn_runner)],
) -> ChatResponse:
    """Return Zoomer's reply to one message in one of the user's conversations.

    The turn is stored with its status, its citations and its tool steps. Only an answer
    that finished normally gets its citations checked, because fallback texts cite nothing.

    Raises:
        ApiError: 401 when nobody is signed in, 429 over the rate limit, 404 when the
            conversation isn't the user's, 409 while another reply in it is running.
    """
    result = await runner.run(turn.id, turn.conversation_id, turn.user_name, turn.message)
    if result.status == "ok":
        citations = check_citations(result.reply, result.retrieved_ids, turn.retrieved_before)
    else:
        citations = Citations(valid=[], invalid=[], missing=False)
    await turns.finish(turn.id, result.status, citations, result.steps)
    return ChatResponse(
        reply=result.reply, turn_id=turn.id, citations=citations, steps=result.steps
    )
