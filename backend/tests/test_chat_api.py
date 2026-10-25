from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.citations import Citations
from app.agent.context import PendingNote
from app.agent.runtime import FALLBACK_TEXT
from app.core.config import Settings
from app.db.models import User
from app.services.cost_report import NOTHING_YET
from app.services.usage import CallUsage
from tests.fakes import (
    FakeConversationStore,
    FakeRateLimiter,
    FakeTurnRunner,
    FakeTurnStore,
    FakeUserStore,
    make_step,
)

# The usage of the fake runner's one model call.
USAGE = {
    "calls": 1,
    "input_tokens": 2000,
    "cached_tokens": 1800,
    "cache_write_tokens": 100,
    "output_tokens": 50,
    "cost_usd": "0.000065500",
}


def test_chat_runs_a_turn_and_returns_its_result(
    client: TestClient,
    user: User,
    fake_conversations: FakeConversationStore,
    fake_turns: FakeTurnStore,
    fake_runner: FakeTurnRunner,
) -> None:
    conversation = fake_conversations.add(user.id)
    fake_turns.add(conversation.id, citations=None, steps=[make_step(["KB-012"])])
    fake_runner.steps = [make_step(["KB-031"])]

    response = client.post(
        "/api/chat", json={"conversation_id": str(conversation.id), "message": "  hi  "}
    )

    assert response.status_code == 200
    [turn] = fake_runner.calls
    assert (turn.conversation_id, turn.user_name, turn.message, turn.retrieved_before) == (
        conversation.id,
        "Mary",
        "hi",
        {"KB-012"},
    )
    assert response.json() == {
        "conversation_id": str(conversation.id),
        "turn_id": str(turn.id),
        "reply": "fake reply",
        "status": "ok",
        "citations": {"valid": [], "invalid": [], "missing": False},
        "steps": [make_step(["KB-031"]).model_dump()],
        "usage": USAGE,
    }
    stored = fake_turns.turns[turn.id]
    assert (stored.status, stored.security_mode) == ("ok", "hardened")


def _events(stream: str) -> list[tuple[str, Any]]:
    """Read a server-sent event stream as (event, data) pairs."""
    events = []
    for block in stream.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_chat_stream_sends_the_turn_as_events(
    client: TestClient,
    user: User,
    fake_conversations: FakeConversationStore,
    fake_runner: FakeTurnRunner,
) -> None:
    conversation = fake_conversations.add(user.id)
    step = make_step(["KB-031"])
    fake_runner.steps = [step]
    note = PendingNote(note_id=uuid.uuid4(), text="Wishlist: Jazz Club")
    fake_runner.pending_notes = [note]
    fake_runner.citations = Citations(valid=["KB-031"])

    response = client.post(
        "/api/chat/stream", json={"conversation_id": str(conversation.id), "message": "hi"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    turn_id = str(fake_runner.calls[0].id)
    assert _events(response.text) == [
        ("start", {"conversation_id": str(conversation.id), "turn_id": turn_id}),
        ("tool_call", {"tool": "search_kb", "args": {"query": "vanilla"}}),
        ("tool_result", step.model_dump()),
        ("pending_note", {"note_id": str(note.note_id), "text": "Wishlist: Jazz Club"}),
        ("token", {"text": "fake reply"}),
        ("citation", {"valid": ["KB-031"], "invalid": [], "missing": False}),
        ("usage", USAGE),
        ("done", {"turn_id": turn_id, "status": "ok", "reply": "fake reply"}),
    ]


def test_cost_command_answers_from_the_stored_calls_without_a_turn(
    client: TestClient,
    settings: Settings,
    user: User,
    fake_conversations: FakeConversationStore,
    fake_turns: FakeTurnStore,
    fake_runner: FakeTurnRunner,
) -> None:
    settings.message_log_enabled = True
    conversation = fake_conversations.add(user.id)
    call = CallUsage("chat", "gpt-6-luna", 2000, 0, 1800, 40)
    fake_turns.add(conversation.id, citations=None, steps=[], calls=[call])

    response = client.post(
        "/api/chat/stream", json={"conversation_id": str(conversation.id), "message": "/cost"}
    )
    new_chat = client.post("/api/chat", json={"message": "/COST"})

    [(event, data)] = _events(response.text)
    assert (event, data["turn_id"], data["status"]) == ("done", None, "ok")
    assert "| 1 | " in data["reply"] and "$0.000265" in data["reply"]
    assert new_chat.json() == {"turn_id": None, "reply": NOTHING_YET, "status": "ok"}
    assert fake_runner.calls == []
    assert len(fake_turns.turns) == 1
    assert len(fake_conversations.conversations) == 1
    logged = fake_conversations.transcripts[conversation.id]
    assert [(message.role, message.kind) for message in logged] == [
        ("user", "command"),
        ("assistant", "command"),
    ]


def test_chat_stream_ends_with_an_error_event_when_the_turn_breaks(
    client: TestClient,
    user: User,
    fake_conversations: FakeConversationStore,
    fake_turns: FakeTurnStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversation = fake_conversations.add(user.id)

    async def broken_finish(*args: Any) -> None:
        raise RuntimeError("database is down")

    monkeypatch.setattr(fake_turns, "finish", broken_finish)

    response = client.post(
        "/api/chat/stream", json={"conversation_id": str(conversation.id), "message": "hi"}
    )

    assert response.status_code == 200
    assert _events(response.text)[-1] == (
        "error",
        {"code": "INTERNAL_ERROR", "message": FALLBACK_TEXT},
    )


@pytest.mark.parametrize(
    "body",
    [
        {"conversation_id": str(uuid.uuid4()), "message": "   "},
        {"conversation_id": str(uuid.uuid4()), "message": "x" * 4001},
        {"conversation_id": "KB-012", "message": "hi"},
    ],
    ids=["blank-message", "message-too-long", "bad-conversation-id"],
)
def test_chat_rejects_invalid_body(
    client: TestClient, user: User, fake_runner: FakeTurnRunner, body: dict[str, str]
) -> None:
    response = client.post("/api/chat", json=body)

    assert response.status_code == 422
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


def test_a_first_message_starts_a_conversation_unless_the_rate_limit_refuses_it(
    client: TestClient,
    user: User,
    fake_conversations: FakeConversationStore,
    fake_limiter: FakeRateLimiter,
    fake_runner: FakeTurnRunner,
) -> None:
    fake_limiter.retry_after = 42
    refused = client.post("/api/chat/stream", json={"message": "vanilla for winter?"})
    fake_limiter.retry_after = None
    response = client.post("/api/chat/stream", json={"message": "vanilla for winter?"})

    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "42"
    assert refused.json()["error"]["code"] == "RATE_LIMITED"
    assert fake_limiter.hits[-1] == (f"chat:user:{user.id}", 20)
    [conversation] = fake_conversations.conversations
    assert (conversation.user_id, conversation.title) == (user.id, "vanilla for winter?")
    [turn] = fake_runner.calls
    assert (turn.conversation_id, turn.retrieved_before) == (conversation.id, set())
    assert _events(response.text)[0] == (
        "start",
        {"conversation_id": str(conversation.id), "turn_id": str(turn.id)},
    )


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
def test_chat_refuses_a_message_while_a_reply_is_running(
    client: TestClient,
    user: User,
    fake_conversations: FakeConversationStore,
    fake_turns: FakeTurnStore,
    fake_runner: FakeTurnRunner,
    path: str,
) -> None:
    conversation = fake_conversations.add(user.id)
    fake_turns.add(conversation.id, citations=None, steps=[], status="running")

    response = client.post(path, json={"conversation_id": str(conversation.id), "message": "hi"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REPLY_IN_PROGRESS"
    assert fake_runner.calls == []
