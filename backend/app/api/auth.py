"""Phone sign-in: a scripted flow driven by code, never by the model.

The web chat shows each ``message`` as a line from Zoomer.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app.api.deps import AppSettings, CurrentUser, Users, limit_sign_in
from app.api.errors import ApiError
from app.core.config import Settings
from app.core.security import SecurityPolicy
from app.core.validators import validate_name, validate_phone
from app.db.models import User
from app.services.auth import sign_in, sign_out

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["auth"])

GREETING = "What are you looking for today?"


class PhoneRequest(BaseModel):
    phone: str = Field(max_length=32)


class CreateUserRequest(BaseModel):
    phone: str = Field(max_length=32)
    name: str = Field(max_length=100)


class UserOut(BaseModel):
    """The signed-in user as the web chat sees them, with the security mode the server
    runs in. The phone is masked."""

    id: uuid.UUID
    name: str
    phone_masked: str
    security: SecurityPolicy

    @classmethod
    def of(cls, user: User, security: SecurityPolicy) -> UserOut:
        masked = user.phone[:4] + "•" * (len(user.phone) - 6) + user.phone[-2:]
        return cls(id=user.id, name=user.name, phone_masked=masked, security=security)


class KnownPhone(BaseModel):
    """The number belongs to a customer, who is now signed in."""

    status: Literal["known"]
    user: UserOut
    message: str


class NewPhone(BaseModel):
    """A new number: the customer gives a name next, to create the account."""

    status: Literal["need_name"]
    # The number in E.164, to send back with the name.
    phone: str
    message: str


class SignInResponse(BaseModel):
    user: UserOut
    message: str


def _security_policy(settings: Settings) -> SecurityPolicy:
    hardened = settings.security_mode == "hardened"
    return SecurityPolicy(
        untrusted_wrap=hardened
        if settings.harden_untrusted_wrap is None
        else settings.harden_untrusted_wrap,
        rw_separation=hardened
        if settings.harden_rw_separation is None
        else settings.harden_rw_separation,
        confirm_notes=hardened
        if settings.harden_confirm_notes is None
        else settings.harden_confirm_notes,
    )


def _valid_phone(raw: str, settings: Settings) -> str:
    phone = validate_phone(raw, settings.phone_default_region)
    if phone is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_PHONE",
            "Hmm, that doesn't look like a phone number. Try the full number, like 067 123 45 67.",
        )
    return phone


@router.post("/auth/phone", dependencies=[Depends(limit_sign_in)])
async def sign_in_with_phone(
    body: PhoneRequest, request: Request, users: Users, settings: AppSettings
) -> KnownPhone | NewPhone:
    """Sign in a known customer by phone number, or ask a new one for their name.

    Raises:
        ApiError: 422 ``INVALID_PHONE``, 429 over the sign-in rate limit.
    """
    phone = _valid_phone(body.phone, settings)
    user = await users.get_by_phone(phone)
    logger.info("sign-in | known=%s", user is not None)
    if user is None:
        return NewPhone(
            status="need_name", phone=phone, message="Nice to meet you! What should I call you?"
        )
    sign_in(request, user)
    return KnownPhone(
        status="known",
        user=UserOut.of(user, _security_policy(settings)),
        message=f"Welcome back, {user.name}! {GREETING}",
    )


@router.post(
    "/auth/create",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_sign_in)],
)
async def create_account(
    body: CreateUserRequest, request: Request, users: Users, settings: AppSettings
) -> SignInResponse:
    """Create an account for a new customer and sign them in.

    Raises:
        ApiError: 422 ``INVALID_PHONE`` or ``INVALID_NAME``, 429 over the sign-in rate limit.
    """
    phone = _valid_phone(body.phone, settings)
    name = validate_name(body.name)
    if name is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_NAME",
            "A name can have letters, spaces, hyphens and apostrophes, 2 to 40 characters. "
            "What should I call you?",
        )
    user = await users.get_or_create(phone, name)
    sign_in(request, user)
    message = f"Nice to meet you, {user.name}! {GREETING}"
    return SignInResponse(user=UserOut.of(user, _security_policy(settings)), message=message)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def log_out(request: Request) -> None:
    """Sign out. Works without a session too, so a stale cookie can always be cleared."""
    sign_out(request)


@router.get("/me")
async def me(user: CurrentUser, settings: AppSettings) -> UserOut:
    """Return the signed-in user and the security mode, or 401 if nobody is signed in."""
    return UserOut.of(user, _security_policy(settings))
