from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.security import SecurityPolicy


class Settings(BaseSettings):
    """The app settings, from the environment and the ``.env`` files."""

    # One .env at the repo root works for a run from the root and from backend/.
    # When both files exist, ./.env wins.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str
    # Retries per request after a timeout, a dropped connection, a 429 or a 5xx.
    openai_max_retries: int = 2
    chat_model: str = "gpt-6-luna"

    # Model calls per turn. A run that needs more ends with a polite "couldn't finish".
    agent_max_turns: int = 5
    # The model gets only the last N user turns of the history. 0 sends all of it.
    history_window_turns: int = 12

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "kb_chunks"
    # The folder with the KB-*.md records, relative to the working directory.
    corpus_dir: Path = Path("corpus")
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # It needs the asyncpg driver: postgresql+asyncpg://...
    database_url: str = "postgresql+asyncpg://zoomer:zoomer@postgres:5432/zoomerfume"
    db_pool_size: int = 10
    db_max_overflow: int = 5
    # Logs every SQL statement.
    db_echo: bool = False
    # When off, the chat still works, but reopened conversations show no transcript.
    message_log_enabled: bool = True

    # Signs the session cookie, e.g. `openssl rand -hex 32`.
    session_secret: str = Field(min_length=32)
    # The region for phone numbers typed without a country code.
    phone_default_region: str = "UA"

    # Fixed one-minute windows: chat messages per user, sign-in attempts per IP.
    rate_limit_chat_per_min: int = 20
    rate_limit_auth_per_min: int = 10

    # "hardened" turns on all three prompt-injection defenses, "vulnerable" turns them off.
    security_mode: Literal["hardened", "vulnerable"] = "hardened"
    # Each one turns a single defense on or off whatever the mode says. Unset follows the mode.
    harden_untrusted_wrap: bool | None = None
    harden_rw_separation: bool | None = None
    harden_confirm_notes: bool | None = None

    debug: bool = False

    @property
    def security(self) -> SecurityPolicy:
        """The prompt-injection defenses that are on: each ``HARDEN_*`` setting, or the
        mode where that setting is unset."""
        hardened = self.security_mode == "hardened"
        overrides = {
            "untrusted_wrap": self.harden_untrusted_wrap,
            "rw_separation": self.harden_rw_separation,
            "confirm_notes": self.harden_confirm_notes,
        }
        return SecurityPolicy(
            **{name: hardened if on is None else on for name, on in overrides.items()}
        )


def get_settings() -> Settings:
    """Load the settings from the environment and the ``.env`` files."""
    return Settings()  # type: ignore[call-arg]
