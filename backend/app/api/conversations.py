"""The signed-in user's conversations and their transcripts."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from app.agent.citations import Citations
from app.agent.context import Step
from app.api.deps import Conversations, CurrentUser, Turns
from app.api.errors import ApiError
from app.db.models import Conversation, Message, User
from app.services.conversations import ConversationStore
from app.services.turns import TurnStore

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationOut(BaseModel):
    """A conversation in the list. ``title`` is empty until the first message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None


class MessageOut(BaseModel):
    """One logged message of a conversation's transcript.

    Zoomer's replies also carry their checked citations and the tool calls behind them.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    turn_id: uuid.UUID | None
    citations: Citations | None = None
    steps: list[Step] = []


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


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(user: CurrentUser, conversations: Conversations) -> ConversationOut:
    """Start an empty conversation."""
    return ConversationOut.model_validate(await conversations.create(user.id))


async def _message_out(turns: TurnStore, message: Message) -> MessageOut:
    out = MessageOut.model_validate(message)
    if message.role == "assistant" and message.turn_id is not None:
        turn = await turns.get(message.turn_id)
        if turn is not None and turn.citations is not None:
            out.citations = Citations.model_validate(turn.citations)
        out.steps = [Step.model_validate(step) for step in await turns.steps(message.turn_id)]
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
    return [
        await _message_out(turns, message)
        for message in await conversations.messages(conversation.id)
    ]
