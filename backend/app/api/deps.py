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


async def get_current_user(
    request: Request, users: Annotated[UserStore, Depends(get_user_store)]
) -> User:
    """Return the signed-in user.

    Raises:
        ApiError: 401 when the request has no valid session, or its user is gone.
    """
    user_id = session_user_id(request)
    user = await users.get(user_id) if user_id else None
    if user is None:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "NOT_SIGNED_IN", "Please sign in first.")
    return user


AppSettings = Annotated[Settings, Depends(get_app_settings)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Users = Annotated[UserStore, Depends(get_user_store)]
