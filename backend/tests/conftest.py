"""Shared fixtures: test settings, a fake turn runner and an API client."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_turn_runner
from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeTurnRunner


@pytest.fixture
def settings() -> Settings:
    """Settings built in code. ``.env`` is never read, so tests can't reach a real key."""
    return Settings(_env_file=None, openai_api_key="test-key", message_log_enabled=False)


@pytest.fixture
def fake_runner() -> FakeTurnRunner:
    return FakeTurnRunner()


@pytest.fixture
def client(settings: Settings, fake_runner: FakeTurnRunner) -> TestClient:
    """API client on the fake runner.

    It is used without ``with``, so the lifespan never runs and nothing connects to
    OpenAI, Postgres or Qdrant.
    """
    app = create_app(settings)
    app.dependency_overrides[get_turn_runner] = lambda: fake_runner
    return TestClient(app)
