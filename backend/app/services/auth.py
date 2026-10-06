"""Customer accounts and the signed session cookie that keeps them signed in."""

from __future__ import annotations

import uuid

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User

SESSION_USER_KEY = "user_id"


class UserStore:
    """Finds and creates users in Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_phone(self, phone: str) -> User | None:
        return await self._session.scalar(select(User).where(User.phone == phone))

    async def get_or_create(self, phone: str, name: str) -> User:
        """Return the user with this phone, creating one with ``name`` if there is none.

        An existing user keeps their name, so two sign-ups with one phone end up
        as one account. It is one upsert: on a conflict, the no-op update makes
        Postgres return the existing row.
        """
        stmt = insert(User).values(id=uuid.uuid4(), phone=phone, name=name)
        stmt = stmt.on_conflict_do_update(
            index_elements=[User.phone], set_={"phone": stmt.excluded.phone}
        ).returning(User)
        user = await self._session.scalar(stmt, execution_options={"populate_existing": True})
        await self._session.commit()
        return user


def sign_in(request: Request, user: User) -> None:
    """Start a fresh session for ``user``. Starlette signs it into the cookie."""
    request.session.clear()
    request.session[SESSION_USER_KEY] = str(user.id)


def sign_out(request: Request) -> None:
    """Forget the signed-in user."""
    request.session.clear()


def session_user_id(request: Request) -> uuid.UUID | None:
    """Return the id of the signed-in user, or ``None`` if nobody is signed in."""
    user_id = request.session.get(SESSION_USER_KEY)
    return uuid.UUID(user_id) if user_id else None
