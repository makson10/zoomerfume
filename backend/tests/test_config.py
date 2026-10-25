"""Settings that must be set, and the database URL built from them."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_need_a_db_password() -> None:
    with pytest.raises(ValidationError, match="db_password"):
        Settings(_env_file=None, openai_api_key="test-key", session_secret="x" * 32)


def test_database_url_keeps_a_password_with_url_characters() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="test-key",
        session_secret="x" * 32,
        db_host="db.local",
        db_password="p@ss:w/rd%",
    )

    url = settings.database_url

    assert url.password == "p@ss:w/rd%"
    assert url.render_as_string(hide_password=True) == (
        "postgresql+asyncpg://zoomer:***@db.local:5432/zoomerfume"
    )
