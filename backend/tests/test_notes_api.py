from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.db.models import User
from tests.fakes import FakeNoteStore, FakeUserStore


async def test_lists_own_notes_newest_first(
    client: TestClient, user: User, fake_users: FakeUserStore, fake_notes: FakeNoteStore
) -> None:
    conversation_id, turn_id = uuid.uuid4(), uuid.uuid4()
    older = await fake_notes.add(user.id, conversation_id, turn_id, "Wishlist: Jazz Club, 100 ml")
    newer = await fake_notes.add(user.id, conversation_id, turn_id, "Ask about the gift wrap")
    stranger = fake_users.add("+48512345678", "Ann")
    await fake_notes.add(stranger.id, uuid.uuid4(), uuid.uuid4(), "Ann's note")

    listed = client.get("/api/notes").json()

    assert [(note["id"], note["text"]) for note in listed] == [
        (str(newer.id), "Ask about the gift wrap"),
        (str(older.id), "Wishlist: Jazz Club, 100 ml"),
    ]


def test_notes_need_a_signed_in_user(client: TestClient) -> None:
    response = client.get("/api/notes")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_SIGNED_IN"
