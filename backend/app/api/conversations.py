"""The signed-in user's conversations and their transcripts."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from app.agent.citations import Citations
from app.agent.context import Step, TurnStatus
from app.api.deps import Conversations, CurrentUser, Turns
from app.api.errors import ApiError
from app.db.models import Conversation, Message, Turn, User
from app.services.conversations import ConversationStore
from app.services.usage import TurnUsage

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationOut(BaseModel):
    """A conversation in the list, titled after its first message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str


class MessageOut(BaseModel):
    """One logged message of a conversation's transcript.

    Zoomer's replies also carry how their turn ended, their checked citations, the tool
    calls behind them and what the turn's model calls cost.
    """

    # Every field is in the response, so the schema marks the defaulted ones required too.
    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )

    id: int
    role: Literal["user", "assistant"]
    content: str
    turn_id: uuid.UUID | None
    # The turn's status, e.g. "cancelled" for a reply the customer stopped.
    status: TurnStatus | None = None
    citations: Citations | None = None
    steps: list[Step] = []
    usage: TurnUsage | None = None


async def require_conversation(
    conversations: ConversationStore, conversation_id: uuid.UUID, user: User
) -> Conversation:
    """Return the user's conversation.

    Raises:
        ApiError: 404 when it doesn't exist or belongs to someone else. Both look
            the same, so nobody can probe for other users' conversation ids.
    """
    conversation = await conversations.get_for_user(conversation_id, user.id)
    if conversation is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Conversation not found.")
    return conversation


@router.get("")
async def list_conversations(
    user: CurrentUser, conversations: Conversations
) -> list[ConversationOut]:
    """Return the user's conversations, the most recently active first."""
    return [
        ConversationOut.model_validate(conversation)
        for conversation in await conversations.list_for_user(user.id)
    ]


def _message_out(
    message: Message, turn: Turn | None, usage: dict[uuid.UUID, TurnUsage]
) -> MessageOut:
    out = MessageOut.model_validate(message)
    if message.role == "assistant" and turn is not None:
        out.status = turn.status
        if turn.citations is not None:
            out.citations = Citations.model_validate(turn.citations)
        out.steps = [Step.model_validate(step) for step in turn.steps]
        out.usage = usage.get(turn.id, TurnUsage.of([]))
    return out


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID, user: CurrentUser, conversations: Conversations, turns: Turns
) -> list[MessageOut]:
    """Return the conversation's transcript, oldest first.

    Raises:
        ApiError: 404 when the conversation isn't the user's.
    """
    conversation = await require_conversation(conversations, conversation_id, user)
    turns_by_id = {turn.id: turn for turn in await turns.for_conversation(conversation.id)}
    usage = await turns.usage_by_turn(conversation.id)
    return [
        _message_out(message, turns_by_id.get(message.turn_id), usage)
        for message in await conversations.messages(conversation.id)
    ]
