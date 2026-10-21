from __future__ import annotations

from fastapi.testclient import TestClient

from app.agent.citations import Citations
from app.db.models import Message, User
from app.services.usage import CallUsage
from tests.fakes import (
    FakeConversationStore,
    FakeNoteStore,
    FakeTurnStore,
    FakeUserStore,
    make_step,
)


def test_lists_own_conversations_most_recent_first(
    client: TestClient,
    user: User,
    fake_users: FakeUserStore,
    fake_conversations: FakeConversationStore,
) -> None:
    older = fake_conversations.add(user.id, "vanilla for winter")
    newer = fake_conversations.add(user.id, "delivery to Lviv")
    fake_conversations.add(fake_users.add("+48512345678", "Ann").id)

    listed = client.get("/api/conversations").json()

    assert listed == [
        {"id": str(newer.id), "title": "delivery to Lviv"},
        {"id": str(older.id), "title": "vanilla for winter"},
    ]


async def test_returns_the_transcript_of_own_conversations_only(
    client: TestClient,
    user: User,
    fake_users: FakeUserStore,
    fake_conversations: FakeConversationStore,
    fake_turns: FakeTurnStore,
    fake_notes: FakeNoteStore,
) -> None:
    own = fake_conversations.add(user.id)
    citations = Citations(valid=["KB-012"], invalid=[], missing=False)
    calls = [
        CallUsage("chat", "gpt-6-luna", 2000, 0, 1800, 40),
        CallUsage("embedding", "text-embedding-3-small", 10),
        CallUsage("chat", "gpt-6-luna", 2600, 1800, 600, 60),
    ]
    turn = fake_turns.add(own.id, citations=citations, steps=[make_step(["KB-012"])], calls=calls)
    fake_conversations.transcripts[own.id] = [
        Message(id=1, role="user", content="hi", turn_id=turn.id),
        Message(id=2, role="assistant", content="hey [KB-012]!", turn_id=turn.id),
    ]
    proposed = await fake_notes.add(user.id, own.id, turn.id, "Wishlist: Jazz Club", "pending")
    await fake_notes.add(user.id, own.id, turn.id, "Saved straight away", "confirmed")
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
            "status": None,
            "citations": None,
            "steps": [],
            "usage": None,
            "notes": [],
        },
        {
            "id": 2,
            "role": "assistant",
            "content": "hey [KB-012]!",
            "turn_id": turn_id,
            "status": "ok",
            "citations": citations.model_dump(),
            "steps": [make_step(["KB-012"]).model_dump()],
            "usage": {
                "calls": 2,
                "input_tokens": 4600,
                "cached_tokens": 1800,
                "cache_write_tokens": 2400,
                "output_tokens": 100,
                "cost_usd": "0.000408200",
            },
            "notes": [
                {
                    "id": str(proposed.id),
                    "text": "Wishlist: Jazz Club",
                    "status": "pending",
                    "created_at": proposed.created_at.isoformat().replace("+00:00", "Z"),
                }
            ],
        },
    ]
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "NOT_FOUND"
