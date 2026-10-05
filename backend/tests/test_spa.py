from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.spa import mount_web_chat
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def web_client(settings: Settings, tmp_path: Path) -> TestClient:
    """API client with a tiny fake frontend build mounted at ``/``."""
    (tmp_path / "index.html").write_text("<!doctype html><title>Zoomerfume</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('zoomer')")
    app = create_app(settings)
    mount_web_chat(app, tmp_path)
    return TestClient(app)


def test_serves_the_page_and_its_assets(web_client: TestClient) -> None:
    page = web_client.get("/")
    asset = web_client.get("/assets/app.js")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "<title>Zoomerfume</title>" in page.text
    assert asset.status_code == 200
    assert asset.text == "console.log('zoomer')"


def test_api_paths_stay_json(web_client: TestClient) -> None:
    missing = web_client.get("/api/nope")

    assert web_client.get("/health").json() == {"status": "ok"}
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Not Found"}


def test_serves_only_the_api_without_a_build(settings: Settings, tmp_path: Path) -> None:
    app = create_app(settings)
    mount_web_chat(app, tmp_path)

    assert TestClient(app).get("/").status_code == 404
