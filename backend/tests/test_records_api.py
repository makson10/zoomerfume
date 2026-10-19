from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.db.models import KbRecord, User
from tests.fakes import FakeKnowledgeBase


def test_returns_a_record_or_404(
    client: TestClient, user: User, fake_kb: FakeKnowledgeBase
) -> None:
    header = {"id": "KB-061", "title": "Delivery", "type": "policy", "updated": "2026-09-01"}
    fake_kb.records["KB-061"] = KbRecord(
        id="KB-061",
        title="Delivery",
        type="policy",
        updated=date(2026, 9, 1),
        header=header,
        body="## Nova Poshta\nTwo days.",
    )

    found = client.get("/api/records/KB-061")
    missing = client.get("/api/records/KB-999")

    assert found.json() == {**header, "header": header, "body": "## Nova Poshta\nTwo days."}
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_records_and_tool_schemas_need_a_signed_in_user(client: TestClient) -> None:
    assert client.get("/api/records/KB-061").status_code == 401
    assert client.get("/api/tools/schema").status_code == 401
