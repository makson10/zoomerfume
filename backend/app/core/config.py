from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # model call (which may batch several parallel tool calls); the Agents SDK
    # raises MaxTurnsExceeded once this is passed. Bounds a pathological tool
    # loop so a confused run can't burn tokens unchecked.
    agent_max_turns: int = 15
    # Conversation-history window. Each turn the agent is fed only the last N
    # user turns verbatim; older turns are dropped from the *model input*
    # (never deleted from the stored session), so input-token cost and latency
    # stay flat on long chats. A "turn" = one user input plus the model's
    # response. 0 disables windowing (the whole session is sent).
    history_window_turns: int = 12
    # Conversation-history age cap. Each turn the agent is fed only turns whose
    # start falls within the last N days; older turns are dropped from the *model
    # input* only. Complements history_window_turns: the age cap forgets stale
    # context when a user returns after days, the turn cap bounds a chatty
    # same-day session. 0 disables the age cap.
    history_retention_days: int = 4

    # ── Qdrant ────────────────────────────────────────────────────────────
    qdrant_url: str = "http://qdrant:6333"

    # ── Database (Postgres) ───────────────────────────────────────────────
    # The async SQLAlchemy DSN. Default targets the compose `postgres` service;
    # the asyncpg driver is required (``postgresql+asyncpg://``).
    database_url: str = "postgresql+asyncpg://zoomer:zoomer@postgres:5432/zoomerfume"
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_echo: bool = False  # True to log every SQL statement (noisy; dev only)
    # Master switch for the message log. When off, writes no-op (the chat
    # behaves identically).
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

    debug: bool = False


def get_settings() -> Settings:
    """Load the settings from the environment and the ``.env`` files."""
    return Settings()  # type: ignore[call-arg]
