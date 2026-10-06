"""Shared fixtures: test settings, fakes for the app's boundaries and an API client."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_conversation_store, get_turn_runner, get_user_store
from app.core.config import Settings
from app.db.models import User
from app.main import create_app
from tests.fakes import FakeConversationStore, FakeTurnRunner, FakeUserStore


@pytest.fixture
def settings() -> Settings:
    """Settings built in code. ``.env`` is never read, so tests can't reach a real key."""
    return Settings(
        _env_file=None,
        openai_api_key="test-key",
        session_secret="test-secret-" + "x" * 32,
        message_log_enabled=False,
    )


@pytest.fixture
def fake_runner() -> FakeTurnRunner:
    return FakeTurnRunner()


@pytest.fixture
def fake_users() -> FakeUserStore:
    return FakeUserStore()


@pytest.fixture
def fake_conversations() -> FakeConversationStore:
    return FakeConversationStore()


@pytest.fixture
def client(
    settings: Settings,
    fake_runner: FakeTurnRunner,
    fake_users: FakeUserStore,
    fake_conversations: FakeConversationStore,
) -> TestClient:
    """API client on the fakes. It keeps cookies between requests, like a browser.

    It is used without ``with``, so the lifespan never runs and nothing connects to
    OpenAI, Postgres or Qdrant.
    """
    app = create_app(settings)
    app.dependency_overrides[get_turn_runner] = lambda: fake_runner
    app.dependency_overrides[get_user_store] = lambda: fake_users
    app.dependency_overrides[get_conversation_store] = lambda: fake_conversations
    return TestClient(app)


@pytest.fixture
def user(client: TestClient, fake_users: FakeUserStore) -> User:
    """A known customer, signed in on ``client``."""
    user = fake_users.add("+380671234567", "Mary")
    client.post("/api/auth/phone", json={"phone": user.phone})
    return user
