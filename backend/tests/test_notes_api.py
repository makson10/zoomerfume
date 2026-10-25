from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import User
from tests.fakes import FakeNoteStore, FakeUserStore


async def test_lists_own_notes_newest_first_without_rejected_ones(
    client: TestClient, user: User, fake_users: FakeUserStore, fake_notes: FakeNoteStore
) -> None:
    conversation_id, turn_id = uuid.uuid4(), uuid.uuid4()
    older = await fake_notes.add(
        user.id, conversation_id, turn_id, "Wishlist: Jazz Club, 100 ml", "confirmed"
    )
    newer = await fake_notes.add(
        user.id, conversation_id, turn_id, "Ask about the gift wrap", "pending"
    )
    await fake_notes.add(user.id, conversation_id, turn_id, "Points alert", "rejected")
    stranger = fake_users.add("+48512345678", "Ann")
    await fake_notes.add(stranger.id, uuid.uuid4(), uuid.uuid4(), "Ann's note", "confirmed")

    listed = client.get("/api/notes").json()

    assert [(note["id"], note["text"], note["status"]) for note in listed] == [
        (str(newer.id), "Ask about the gift wrap", "pending"),
        (str(older.id), "Wishlist: Jazz Club, 100 ml", "confirmed"),
    ]


@pytest.mark.parametrize(("action", "status"), [("confirm", "confirmed"), ("reject", "rejected")])
async def test_the_customer_decides_once_on_own_pending_notes_only(
    client: TestClient,
    user: User,
    fake_users: FakeUserStore,
    fake_notes: FakeNoteStore,
    action: str,
    status: str,
) -> None:
    note = await fake_notes.add(user.id, uuid.uuid4(), uuid.uuid4(), "Wishlist", "pending")
    stranger = fake_users.add("+48512345678", "Ann")
    foreign = await fake_notes.add(stranger.id, uuid.uuid4(), uuid.uuid4(), "Ann's", "pending")

    decided = client.post(f"/api/notes/{note.id}/{action}")
    again = client.post(f"/api/notes/{note.id}/confirm")
    hidden = client.post(f"/api/notes/{foreign.id}/{action}")

    assert decided.status_code == 200
    assert (decided.json()["id"], decided.json()["status"]) == (str(note.id), status)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "NOTE_DECIDED")
    assert note.status == status
    assert hidden.status_code == 404
    assert foreign.status == "pending"
