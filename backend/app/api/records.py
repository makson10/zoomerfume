"""Knowledge base records, for the citation chips in the web chat."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import Knowledge, get_current_user
from app.api.errors import ApiError
from app.kb.corpus import RecordType

router = APIRouter(
    prefix="/api/records", tags=["records"], dependencies=[Depends(get_current_user)]
)


class RecordOut(BaseModel):
    """A full knowledge base record: its header fields and its Markdown body."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    type: RecordType
    updated: date
    header: dict[str, Any]
    body: str


@router.get("/{record_id}")
async def get_record(record_id: str, kb: Knowledge) -> RecordOut:
    """Return one knowledge base record in full.

    Raises:
        ApiError: 401 when nobody is signed in, 404 when there is no record with this id.
    """
    record = await kb.get_record(record_id)
    if record is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Record not found.")
    return RecordOut.model_validate(record)
