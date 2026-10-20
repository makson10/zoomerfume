"""The signed-in user's notes, for the notes panel in the web chat."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentUser, Notes

router = APIRouter(prefix="/api/notes", tags=["notes"])

# The panel shows the newest notes only.
NOTES_LIMIT = 100


class NoteOut(BaseModel):
    """One of the customer's notes."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    created_at: datetime


@router.get("")
async def list_notes(user: CurrentUser, notes: Notes) -> list[NoteOut]:
    """Return the user's notes, the newest first, at most :data:`NOTES_LIMIT` of them."""
    return [
        NoteOut.model_validate(note) for note in await notes.list_for_user(user.id, NOTES_LIMIT)
    ]
