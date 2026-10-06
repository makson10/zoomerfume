from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.models import User
from tests.fakes import FakeConversationStore, FakeTurnRunner, FakeUserStore


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_the_runner_reply(
    client: TestClient,
    user: User,
    fake_conversations: FakeConversationStore,
    fake_runner: FakeTurnRunner,
) -> None:
    conversation = fake_conversations.add(user.id)

    response = client.post(
        "/api/chat", json={"conversation_id": str(conversation.id), "message": "  hi  "}
    )

    assert response.status_code == 200
    assert response.json() == {"reply": FakeTurnRunner.reply}
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
