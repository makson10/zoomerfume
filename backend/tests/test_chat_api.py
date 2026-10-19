from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import User
from tests.fakes import (
    FakeConversationStore,
    FakeRateLimiter,
    FakeTurnRunner,
    FakeTurnStore,
    FakeUserStore,
    make_step,
)


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_the_reply_with_citations_and_steps(
    client: TestClient,
    user: User,
    fake_conversations: FakeConversationStore,
    fake_turns: FakeTurnStore,
    fake_runner: FakeTurnRunner,
) -> None:
    conversation = fake_conversations.add(user.id)
    fake_turns.add(conversation.id, citations=None, steps=[make_step(["KB-012"])])
    fake_runner.reply = "Try KB-031 [KB-031], or KB-012 from before [KB-012], not [KB-099]."
    fake_runner.steps = [make_step(["KB-031"])]

    response = client.post(
        "/api/chat", json={"conversation_id": str(conversation.id), "message": "  hi  "}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == fake_runner.reply
    assert body["citations"] == {
        "valid": ["KB-031", "KB-012"],
        "invalid": ["KB-099"],
        "missing": False,
    }
    assert body["steps"] == [make_step(["KB-031"]).model_dump()]
    turn = fake_turns.turns[uuid.UUID(body["turn_id"])]
    assert (turn.status, turn.citations) == ("ok", body["citations"])
    assert fake_runner.calls == [(conversation.id, "Mary", "hi")]
    assert conversation.title == "hi"


@pytest.mark.parametrize(
    "body",
    [
        {"conversation_id": str(uuid.uuid4()), "message": "   "},
        {"conversation_id": str(uuid.uuid4()), "message": "x" * 4001},
        {"message": "hi"},
    ],
    ids=["blank-message", "message-too-long", "missing-conversation-id"],
)
def test_chat_rejects_invalid_body(
    client: TestClient, user: User, fake_runner: FakeTurnRunner, body: dict[str, str]
) -> None:
    response = client.post("/api/chat", json=body)

    assert response.status_code == 422
    assert fake_runner.calls == []


def test_chat_needs_a_signed_in_user(client: TestClient, fake_runner: FakeTurnRunner) -> None:
    body = {"conversation_id": str(uuid.uuid4()), "message": "hi"}

    response = client.post("/api/chat", json=body)

    assert response.status_code == 401
    assert fake_runner.calls == []


def test_chat_hides_other_users_conversations(
    client: TestClient,
    user: User,
    fake_users: FakeUserStore,
    fake_conversations: FakeConversationStore,
    fake_runner: FakeTurnRunner,
) -> None:
    stranger = fake_users.add("+48512345678", "Ann")
    conversation = fake_conversations.add(stranger.id)

    response = client.post(
        "/api/chat", json={"conversation_id": str(conversation.id), "message": "hi"}
    )

    assert response.status_code == 404
    assert fake_runner.calls == []


def test_chat_over_the_rate_limit_gets_429(
    client: TestClient,
    user: User,
    fake_conversations: FakeConversationStore,
    fake_limiter: FakeRateLimiter,
    fake_runner: FakeTurnRunner,
) -> None:
    conversation = fake_conversations.add(user.id)
    fake_limiter.retry_after = 42

    response = client.post(
        "/api/chat", json={"conversation_id": str(conversation.id), "message": "hi"}
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert fake_limiter.hits[-1] == (f"chat:user:{user.id}", 20)
    assert fake_runner.calls == []
