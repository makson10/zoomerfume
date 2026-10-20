"""Chat endpoints: one user message in, Zoomer's reply out, streamed or in one piece."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, ConfigDict, Field

from app.agent.citations import Citations
from app.agent.context import Step, TurnStatus
from app.agent.runtime import FALLBACK_TEXT, NewTurn, TurnResult
from app.agent.streaming import Token, ToolCall
from app.api.conversations import require_conversation
from app.api.deps import Conversations, CurrentUser, Runtime, Turns, limit_chat
from app.api.errors import ApiError, ErrorDetail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    conversation_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)


class TurnDone(BaseModel):
    """The ``done`` event: the stored reply, which replaces the streamed text."""

    turn_id: uuid.UUID
    reply: str
    status: TurnStatus


# The ``data`` of each stream event, in event order: token, tool_call, tool_result,
# citation, done, or error.
ChatEventData = Token | ToolCall | Step | Citations | TurnDone | ErrorDetail


async def start_turn(
    body: ChatRequest, user: CurrentUser, conversations: Conversations, turns: Turns
) -> NewTurn:
    """Start a turn for the message in one of the user's conversations.

    It runs as a dependency, before a streamed reply sends anything, so its errors are
    plain HTTP errors. The reads come first and both writes commit, so no transaction
    stays open on the request's session while the turn runs.

    Raises:
        ApiError: 404 when the conversation isn't the user's, 409 while Zoomer is still
            answering another message in it.
    """
    conversation = await require_conversation(conversations, body.conversation_id, user)
    retrieved_before = await turns.retrieved_ids(conversation.id)
    turn_id = await turns.start(conversation.id)
    if turn_id is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "REPLY_IN_PROGRESS",
            "I'm still answering your last message in this chat. "
            "Wait for my reply or stop it, then send this one again.",
        )
    await conversations.mark_active(conversation, body.message)
    return NewTurn(turn_id, conversation.id, user.name, body.message, retrieved_before)


StartedTurn = Annotated[NewTurn, Depends(start_turn)]

# FastAPI documents a response model in the route's media type, but errors are JSON
# even on the stream route.
STREAM_ERROR_RESPONSES = {
    "4XX": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorBody"}}}}
}


@router.post("/chat", dependencies=[Depends(limit_chat)])
async def chat(turn: StartedTurn, turns: Turns, runner: Runtime) -> TurnResult:
    """Return Zoomer's reply to one message in one of the user's conversations.

    It runs the same turn as ``/api/chat/stream`` and returns the stream's last event.

    Raises:
        ApiError: 401 when nobody is signed in, 429 over the rate limit, 404 when the
            conversation isn't the user's, 409 while another reply in it is running.
    """
    events = [event async for event in runner.stream(turn, turns)]
    return events[-1]


@router.post(
    "/chat/stream",
    response_class=EventSourceResponse,
    responses=STREAM_ERROR_RESPONSES,
    dependencies=[Depends(limit_chat)],
)
async def chat_stream(
    turn: StartedTurn, turns: Turns, runner: Runtime
) -> AsyncIterator[ChatEventData]:
    """Stream Zoomer's reply to one message as server-sent events.

    ``token`` events carry the reply as the model writes it, and each tool call sends
    ``tool_call`` and then ``tool_result`` with its step. The stream ends with
    ``citation`` and ``done``. ``done`` carries the stored reply, which replaces the
    streamed text, because the fallback and step-limit texts are never streamed.
    ``error`` ends a stream that broke. Closing the connection stops the turn.

    The return type lists the events' data models for the OpenAPI schema. Each one is
    sent as a ``ServerSentEvent`` with its event name.

    Raises:
        ApiError: Before the stream starts, the same errors as ``/api/chat``.
    """
    try:
        async with aclosing(runner.stream(turn, turns)) as events:
            async for event in events:
                match event:
                    case Token():
                        yield ServerSentEvent(event="token", data=event)
                    case ToolCall():
                        yield ServerSentEvent(event="tool_call", data=event)
                    case Step():
                        yield ServerSentEvent(event="tool_result", data=event)
                    case TurnResult():
                        yield ServerSentEvent(event="citation", data=event.citations)
                        done = TurnDone(
                            turn_id=event.turn_id, reply=event.reply, status=event.status
                        )
                        yield ServerSentEvent(event="done", data=done)
    except Exception:
        logger.exception("chat stream failed | turn=%s", turn.id)
        error = ErrorDetail(code="INTERNAL_ERROR", message=FALLBACK_TEXT)
        yield ServerSentEvent(event="error", data=error)
