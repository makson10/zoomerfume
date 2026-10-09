"""FastAPI dependencies that hand routes the objects built in the app lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runtime import TurnRunner
from app.api.errors import ApiError
from app.core.config import Settings
from app.db.models import User
from app.services.auth import UserStore, session_user_id
from app.services.conversations import ConversationStore
from app.services.rate_limit import RateLimiter


def get_turn_runner(request: Request) -> TurnRunner:
    """Return the turn runner the lifespan stored on ``app.state``."""
    return request.app.state.turn_runner


def get_app_settings(request: Request) -> Settings:
    """Return the settings the app was created with."""
    return request.app.state.settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session for one request."""
    async with request.app.state.sessionmaker() as session:
        yield session


def get_user_store(db: Annotated[AsyncSession, Depends(get_db)]) -> UserStore:
    return UserStore(db)


def get_conversation_store(db: Annotated[AsyncSession, Depends(get_db)]) -> ConversationStore:
    return ConversationStore(db)


def get_rate_limiter(db: Annotated[AsyncSession, Depends(get_db)]) -> RateLimiter:
    return RateLimiter(db)


AppSettings = Annotated[Settings, Depends(get_app_settings)]
Conversations = Annotated[ConversationStore, Depends(get_conversation_store)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
Users = Annotated[UserStore, Depends(get_user_store)]


async def get_current_user(request: Request, users: Users) -> User:
    """Return the signed-in user.

    Raises:
        ApiError: 401 when the request has no valid session, or its user is gone.
    """
    user_id = session_user_id(request)
    user = await users.get(user_id) if user_id else None
    if user is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "NOT_SIGNED_IN", "Please sign in first.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def _enforce(limiter: RateLimiter, key: str, limit: int, message: str) -> None:
    retry_after = await limiter.hit(key, limit)
    if retry_after is not None:
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "RATE_LIMITED",
            message,
            headers={"Retry-After": str(retry_after)},
        )


async def limit_chat(user: CurrentUser, limiter: Limiter, settings: AppSettings) -> None:
    """Allow ``RATE_LIMIT_CHAT_PER_MIN`` chat messages per user per minute.

    Raises:
        ApiError: 429 with ``Retry-After`` when the user is over the limit.
    """
    await _enforce(
        limiter,
        f"chat:user:{user.id}",
        settings.rate_limit_chat_per_min,
        "Whoa, that's a lot of messages at once! Give me a minute and try again.",
    )


async def limit_sign_in(request: Request, limiter: Limiter, settings: AppSettings) -> None:
    """Allow ``RATE_LIMIT_AUTH_PER_MIN`` sign-in attempts per client IP per minute.

    Raises:
        ApiError: 429 with ``Retry-After`` when the IP is over the limit.
    """
    client_ip = request.client.host if request.client else "unknown"
    await _enforce(
        limiter,
        f"auth:ip:{client_ip}",
        settings.rate_limit_auth_per_min,
        "Too many sign-in attempts. Please wait a minute and try again.",
    )
