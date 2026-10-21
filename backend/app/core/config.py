from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.security import SecurityPolicy


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # One .env at the repo root serves both a run from the repo root and a
        # local run from backend/. When both files exist, ./.env wins.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── OpenAI ────────────────────────────────────────────────────────────
    openai_api_key: str
    # Transient-failure retries the OpenAI client makes per request before
    # raising (timeouts, connection drops, 429, 5xx). N retries means N+1 total
    # attempts, so the default of 2 gives a 3-attempt cap.
    openai_max_retries: int = 2
    # Model behind Zoomer's replies.
    chat_model: str = "gpt-6-luna"

    # ── Agent runtime ─────────────────────────────────────────────────────
    # Hard ceiling on agent-loop iterations per turn. One "turn" is a single
    # model call (which may batch several parallel tool calls). A run that needs
    # more ends with a polite "couldn't finish" answer, so a confused tool loop
    # can't burn tokens unchecked.
    agent_max_turns: int = 5
    # Conversation-history window. Each turn the agent is fed only the last N
    # user turns verbatim; older turns are dropped from the *model input*
    # (never deleted from the stored session), so input-token cost and latency
    # stay flat on long chats. A "turn" = one user input plus the model's
    # response. 0 disables windowing (the whole session is sent).
    history_window_turns: int = 12

    # ── Knowledge base ────────────────────────────────────────────────────
    qdrant_url: str = "http://qdrant:6333"
    # Qdrant collection that holds the embedded corpus chunks.
    qdrant_collection: str = "kb_chunks"
    # Folder with the KB-*.md records, relative to the working directory.
    corpus_dir: Path = Path("corpus")
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # ── Database (Postgres) ───────────────────────────────────────────────
    # The async SQLAlchemy DSN. Default targets the compose `postgres` service;
    # the asyncpg driver is required (``postgresql+asyncpg://``).
    database_url: str = "postgresql+asyncpg://zoomer:zoomer@postgres:5432/zoomerfume"
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_echo: bool = False  # True to log every SQL statement (noisy; dev only)
    # Master switch for the message log. When off, writes no-op: the chat still
    # works, but reopened conversations show no transcript.
    message_log_enabled: bool = True

    # ── Sign-in ───────────────────────────────────────────────────────────
    # Signs the session cookie. A long random string, e.g. `openssl rand -hex 32`.
    session_secret: str = Field(min_length=32)
    # Region used to read phone numbers typed without a country code.
    phone_default_region: str = "UA"

    # ── Rate limits ───────────────────────────────────────────────────────
    # Fixed one-minute windows: chat messages per user, sign-in attempts per IP.
    rate_limit_chat_per_min: int = 20
    rate_limit_auth_per_min: int = 10

    # ── Prompt-injection defenses ─────────────────────────────────────────
    # "hardened" turns on all three defenses, "vulnerable" turns them all off.
    security_mode: Literal["hardened", "vulnerable"] = "hardened"
    # Turn one defense on or off whatever the mode says. Unset follows the mode.
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
