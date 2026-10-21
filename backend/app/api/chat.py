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
from app.agent.context import PendingNote, Step, TurnStatus
from app.agent.runtime import FALLBACK_TEXT, NewTurn, TurnResult, TurnStart
from app.agent.streaming import Token, ToolCall
from app.api.conversations import require_conversation
from app.api.deps import AppSettings, Conversations, CurrentUser, Runtime, Turns, limit_chat
from app.api.errors import ApiError, ErrorDetail
from app.core.config import Settings
from app.db.models import User
from app.services.conversations import ConversationStore
from app.services.cost_report import COST_COMMAND, NOTHING_YET, cost_report
from app.services.turns import TurnStore
from app.services.usage import TurnUsage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    # Leave it out to start a new conversation with this message.
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=4000)


class TurnDone(BaseModel):
    """The ``done`` event: the stored reply, which replaces the streamed text.

    It is also the whole answer to a chat command such as ``/cost``, which runs no turn.
    """

    # Empty for a chat command's reply.
    turn_id: uuid.UUID | None
    reply: str
    status: TurnStatus


# The ``data`` of each stream event, in event order: start, token, tool_call, tool_result,
# pending_note, citation, usage, done, or error.
ChatEventData = (
    TurnStart
    | Token
    | ToolCall
    | Step
    | PendingNote
    | Citations
    | TurnUsage
    | TurnDone
    | ErrorDetail
)


async def start_turn(
    body: ChatRequest,
    user: User,
    conversations: ConversationStore,
    turns: TurnStore,
    settings: Settings,
) -> NewTurn:
    """Start a turn for the message in one of the user's conversations, or in a new one.

    A new conversation is created only here, after the sign-in and rate limit checks, so a
    refused message leaves no empty chat behind. The reads come first and every write
    commits, so no transaction stays open on the request's session while the turn runs.
    The turn stores the security mode it runs with.

    Raises:
        ApiError: 404 when the conversation isn't the user's, 409 while Zoomer is still
            answering another message in it.
    """
    if body.conversation_id is None:
        conversation = await conversations.create(user.id, body.message)
        retrieved_before: set[str] = set()
    else:
        conversation = await require_conversation(conversations, body.conversation_id, user)
        retrieved_before = await turns.retrieved_ids(conversation.id)
    turn_id = await turns.start(conversation.id, settings.security.mode)
    if turn_id is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "REPLY_IN_PROGRESS",
            "I'm still answering your last message in this chat. "
            "Wait for my reply or stop it, then send this one again.",
        )
    await conversations.mark_active(conversation)
    return NewTurn(turn_id, conversation.id, user.id, user.name, body.message, retrieved_before)


async def answer_cost_command(
    body: ChatRequest, user: User, conversations: ConversationStore, turns: TurnStore, log: bool
) -> TurnDone:
    """Answer ``/cost`` with the conversation's cost report, without the model.

    The command and the report go to the message log, so the transcript shows them, but
    never to Zoomer's history. In a new chat there is nothing to count, so nothing is
    created.

    Raises:
        ApiError: 404 when the conversation isn't the user's.
    """
    if body.conversation_id is None:
        return TurnDone(turn_id=None, reply=NOTHING_YET, status="ok")
    conversation = await require_conversation(conversations, body.conversation_id, user)
    report = cost_report(
        await turns.for_conversation(conversation.id), await turns.usage_by_turn(conversation.id)
    )
    if log:
        await conversations.log_command(conversation.id, body.message, report)
    return TurnDone(turn_id=None, reply=report, status="ok")


async def start_reply(
    body: ChatRequest,
    user: CurrentUser,
    conversations: Conversations,
    turns: Turns,
    settings: AppSettings,
) -> NewTurn | TurnDone:
    """Answer a chat command right away, or start a turn for the message.

    It runs as a dependency, before a streamed reply sends anything, so its errors are
    plain HTTP errors.
    """
    if body.message.lower() == COST_COMMAND:
        return await answer_cost_command(
            body, user, conversations, turns, settings.message_log_enabled
        )
    return await start_turn(body, user, conversations, turns, settings)


StartedReply = Annotated[NewTurn | TurnDone, Depends(start_reply)]

# FastAPI documents a response model in the route's media type, but errors are JSON
# even on the stream route.
STREAM_ERROR_RESPONSES = {
    "4XX": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorBody"}}}}
}


@router.post("/chat", dependencies=[Depends(limit_chat)])
async def chat(started: StartedReply, turns: Turns, runner: Runtime) -> TurnResult | TurnDone:
    """Return Zoomer's reply to one message in one of the user's conversations, or in a
    new one.

    It runs the same turn as ``/api/chat/stream`` and returns the stream's last event. A
    chat command such as ``/cost`` gets its reply as a ``TurnDone``.

    Raises:
        ApiError: 401 when nobody is signed in, 429 over the rate limit, 404 when the
            conversation isn't the user's, 409 while another reply in it is running.
    """
    if isinstance(started, TurnDone):
        return started
    events = [event async for event in runner.stream(started, turns)]
    return events[-1]


@router.post(
    "/chat/stream",
    response_class=EventSourceResponse,
    responses=STREAM_ERROR_RESPONSES,
    dependencies=[Depends(limit_chat)],
)
async def chat_stream(
    started: StartedReply, turns: Turns, runner: Runtime
) -> AsyncIterator[ChatEventData]:
    """Stream Zoomer's reply to one message as server-sent events.

    ``start`` names the conversation and the turn, which is how the web chat learns the id
    of a new conversation. ``token`` events carry the reply as the model writes it, and each
    tool call sends ``tool_call`` and then ``tool_result`` with its step. A note that waits
    for the customer's confirmation follows its step as ``pending_note``. The stream ends
    with ``citation``, ``usage`` (the turn's tokens and cost) and ``done``. ``done`` carries
    the stored reply, which replaces the streamed text, because the fallback and step-limit
    texts are never streamed. ``error`` ends a stream that broke. Closing the connection
    stops the turn. A chat command such as ``/cost`` runs no turn: its stream is a single
    ``done``.

    The return type lists the events' data models for the OpenAPI schema. Each one is
    sent as a ``ServerSentEvent`` with its event name.

    Raises:
        ApiError: Before the stream starts, the same errors as ``/api/chat``.
    """
    if isinstance(started, TurnDone):
        yield ServerSentEvent(event="done", data=started)
        return
    try:
        async with aclosing(runner.stream(started, turns)) as events:
            async for event in events:
                match event:
                    case TurnStart():
                        yield ServerSentEvent(event="start", data=event)
                    case Token():
                        yield ServerSentEvent(event="token", data=event)
                    case ToolCall():
                        yield ServerSentEvent(event="tool_call", data=event)
                    case Step():
                        yield ServerSentEvent(event="tool_result", data=event)
                    case PendingNote():
                        yield ServerSentEvent(event="pending_note", data=event)
                    case TurnResult():
                        yield ServerSentEvent(event="citation", data=event.citations)
                        yield ServerSentEvent(event="usage", data=event.usage)
                        done = TurnDone(
                            turn_id=event.turn_id, reply=event.reply, status=event.status
                        )
                        yield ServerSentEvent(event="done", data=done)
    except Exception:
        logger.exception("chat stream failed | turn=%s", started.id)
        error = ErrorDetail(code="INTERNAL_ERROR", message=FALLBACK_TEXT)
        yield ServerSentEvent(event="error", data=error)
