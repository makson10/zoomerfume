from __future__ import annotations

from fastapi.testclient import TestClient

from app.agent.citations import Citations
from app.db.models import Message, User
from tests.fakes import FakeConversationStore, FakeTurnStore, FakeUserStore, make_step


def test_lists_own_conversations_most_recent_first(
    client: TestClient,
    user: User,
    fake_users: FakeUserStore,
    fake_conversations: FakeConversationStore,
) -> None:
    older = client.post("/api/conversations").json()
    newer = client.post("/api/conversations").json()
    fake_conversations.add(fake_users.add("+48512345678", "Ann").id)

    listed = client.get("/api/conversations").json()

    assert older == {"id": older["id"], "title": None}
    assert [c["id"] for c in listed] == [newer["id"], older["id"]]


def test_returns_the_transcript_of_own_conversations_only(
    client: TestClient,
    user: User,
    fake_users: FakeUserStore,
    fake_conversations: FakeConversationStore,
    fake_turns: FakeTurnStore,
) -> None:
    own = fake_conversations.add(user.id)
    citations = Citations(valid=["KB-012"], invalid=[], missing=False)
    turn = fake_turns.add(own.id, citations=citations, steps=[make_step(["KB-012"])])
    fake_conversations.transcripts[own.id] = [
        Message(id=1, role="user", content="hi", turn_id=turn.id),
        Message(id=2, role="assistant", content="hey [KB-012]!", turn_id=turn.id),
    ]
    foreign = fake_conversations.add(fake_users.add("+48512345678", "Ann").id)

    transcript = client.get(f"/api/conversations/{own.id}/messages")
    hidden = client.get(f"/api/conversations/{foreign.id}/messages")

    turn_id = str(turn.id)
    assert transcript.json() == [
        {
            "id": 1,
            "role": "user",
            "content": "hi",
            "turn_id": turn_id,
            "citations": None,
            "steps": [],
        },
        {
            "id": 2,
            "role": "assistant",
            "content": "hey [KB-012]!",
            "turn_id": turn_id,
            "citations": citations.model_dump(),
            "steps": [make_step(["KB-012"]).model_dump()],
        },
    ]
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "NOT_FOUND"
