"""The signed-in user's notes, for the notes panel in the web chat, and the customer's
decisions on the notes Zoomer proposes."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentUser, Notes
from app.api.errors import ApiError
from app.db.models import User
from app.services.notes import NoteStatus, NoteStore

router = APIRouter(prefix="/api/notes", tags=["notes"])

# The panel shows the newest notes only.
NOTES_LIMIT = 100


class NoteOut(BaseModel):
    """One of the customer's notes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    status: NoteStatus
    created_at: datetime


@router.get("")
async def list_notes(user: CurrentUser, notes: Notes) -> list[NoteOut]:
    """Return the user's notes, the newest first, at most :data:`NOTES_LIMIT` of them.

    Pending notes are included, rejected ones are not.
    """
    return [
        NoteOut.model_validate(note) for note in await notes.list_for_user(user.id, NOTES_LIMIT)
    ]


async def _decide(
    notes: NoteStore, note_id: uuid.UUID, user: User, decision: NoteStatus
) -> NoteOut:
    note = await notes.decide(note_id, user.id, decision)
    if note is not None:
        return NoteOut.model_validate(note)
    if await notes.get_for_user(note_id, user.id) is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Note not found.")
    raise ApiError(
        status.HTTP_409_CONFLICT,
        "NOTE_DECIDED",
        "You've already saved or dropped this note, maybe in another tab.",
    )


@router.post("/{note_id}/confirm")
async def confirm_note(note_id: uuid.UUID, user: CurrentUser, notes: Notes) -> NoteOut:
    """Save a note Zoomer proposed. Only the customer can do this, from the web chat: the
    model has no tool for it.

    Raises:
        ApiError: 404 when the user has no such note, 409 when it was already decided.
    """
    return await _decide(notes, note_id, user, "confirmed")


@router.post("/{note_id}/reject")
async def reject_note(note_id: uuid.UUID, user: CurrentUser, notes: Notes) -> NoteOut:
    """Drop a note Zoomer proposed. It leaves the notes panel.

    Raises:
        ApiError: 404 when the user has no such note, 409 when it was already decided.
    """
    return await _decide(notes, note_id, user, "rejected")
