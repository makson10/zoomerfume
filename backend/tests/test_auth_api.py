from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeRateLimiter, FakeUserStore

PHONE = "+380671234567"


def test_known_phone_signs_in(client: TestClient, fake_users: FakeUserStore) -> None:
    fake_users.add(PHONE, "Mary")

    response = client.post("/api/auth/phone", json={"phone": "067 123 45 67"})

    assert response.status_code == 200
    assert response.json()["status"] == "known"
    assert client.get("/api/me").json()["phone_masked"] == "+380•••••••67"


def test_new_phone_asks_for_a_name_then_signs_in(
    client: TestClient, fake_users: FakeUserStore
) -> None:
    asked = client.post("/api/auth/phone", json={"phone": "067 123 45 67"})

    assert asked.json()["status"] == "need_name"
    assert client.get("/api/me").status_code == 401

    created = client.post("/api/auth/create", json={"phone": asked.json()["phone"], "name": "Mary"})

    assert created.status_code == 201
    assert client.get("/api/me").json()["name"] == "Mary"
    assert [user.phone for user in fake_users.users.values()] == [PHONE]


@pytest.mark.parametrize(
    ("path", "body", "code"),
    [
        ("/api/auth/phone", {"phone": "12345"}, "INVALID_PHONE"),
        ("/api/auth/create", {"phone": PHONE, "name": "M"}, "INVALID_NAME"),
    ],
    ids=["phone", "name"],
)
def test_sign_in_rejects_invalid_input(
    client: TestClient, fake_users: FakeUserStore, path: str, body: dict[str, str], code: str
) -> None:
    response = client.post(path, json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code
    assert fake_users.users == {}


def test_logout_ends_the_session(client: TestClient, fake_users: FakeUserStore) -> None:
    fake_users.add(PHONE, "Mary")
    client.post("/api/auth/phone", json={"phone": PHONE})

    assert client.post("/api/auth/logout").status_code == 204

    me = client.get("/api/me")
    assert me.status_code == 401
    assert me.json()["error"]["code"] == "NOT_SIGNED_IN"


def test_sign_in_over_the_rate_limit_gets_429(
    client: TestClient, fake_users: FakeUserStore, fake_limiter: FakeRateLimiter
) -> None:
    fake_users.add(PHONE, "Mary")
    fake_limiter.retry_after = 30

    response = client.post("/api/auth/phone", json={"phone": PHONE})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert fake_limiter.hits == [("auth:ip:testclient", 10)]
    assert client.get("/api/me").status_code == 401
