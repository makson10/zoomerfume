"""The readiness probe, and /api/whoami with the X-Served-By header."""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_readiness
from app.services.readiness import Readiness, migration_head
from tests.fakes import FakeEngine, FakeQdrant

HEAD = migration_head()


def use_readiness(client: TestClient, engine: FakeEngine, qdrant: FakeQdrant) -> None:
    readiness = Readiness(engine, qdrant, "kb_chunks", HEAD)  # type: ignore[arg-type]
    client.app.dependency_overrides[get_readiness] = lambda: readiness


def test_ready_when_every_check_passes(client: TestClient) -> None:
    use_readiness(client, FakeEngine(HEAD), FakeQdrant(points=208))

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"postgres": "ok", "migrations": "ok", "qdrant": "ok"},
    }


def test_not_ready_until_migrated_and_ingested(client: TestClient) -> None:
    use_readiness(client, FakeEngine("0001"), FakeQdrant(points=0))

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "postgres": "ok",
            "migrations": f"at 0001, head is {HEAD}",
            "qdrant": "empty collection",
        },
    }


def test_a_hanging_or_failing_service_is_reported_without_details(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.readiness.CHECK_TIMEOUT_S", 0.01)
    use_readiness(
        client, FakeEngine(HEAD, delay_s=1), FakeQdrant(error=ConnectionError("qdrant:6333"))
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {
        "postgres": "timeout",
        "migrations": "timeout",
        "qdrant": "unavailable",
    }
    assert "6333" not in response.text


def test_whoami_and_every_response_name_the_replica(client: TestClient) -> None:
    response = client.get("/api/whoami")

    assert response.json() == {"hostname": socket.gethostname(), "version": "dev"}
    assert client.get("/health").headers["X-Served-By"] == socket.gethostname()
