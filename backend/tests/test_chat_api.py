from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeTurnRunner


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_the_runner_reply(client: TestClient, fake_runner: FakeTurnRunner) -> None:
    response = client.post("/api/chat", json={"session_id": " demo ", "message": "  hi  "})

    assert response.status_code == 200
    assert response.json() == {"reply": FakeTurnRunner.reply}
    assert fake_runner.calls == [("demo", "hi")]


@pytest.mark.parametrize(
    "body",
    [
        {"session_id": "demo", "message": "   "},
        {"session_id": "demo", "message": "x" * 4001},
        {"message": "hi"},
    ],
    ids=["blank-message", "message-too-long", "missing-session-id"],
)
def test_chat_rejects_invalid_body(
    client: TestClient, fake_runner: FakeTurnRunner, body: dict[str, str]
) -> None:
    response = client.post("/api/chat", json=body)

    assert response.status_code == 422
    assert fake_runner.calls == []
