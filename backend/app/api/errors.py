"""API errors with a stable JSON body the web chat can show to the customer."""

from __future__ import annotations

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """What went wrong: a stable code and a short text for the customer."""

    # A stable machine-readable code, e.g. "INVALID_PHONE".
    code: str
    message: str


class ErrorBody(BaseModel):
    """The body of every API error response."""

    error: ErrorDetail


# Every 4XX response of an API route has this body, validation errors included.
ERROR_RESPONSES = {"4XX": {"model": ErrorBody}}


class ApiError(Exception):
    """An error response with the body ``{"error": {"code": ..., "message": ...}}``.

    Args:
        status_code: The HTTP status.
        code: A stable machine-readable code, e.g. ``INVALID_PHONE``.
        message: A short text for the customer.
        headers: Extra response headers, e.g. ``Retry-After``.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Render an :class:`ApiError` as its JSON body."""
    body = ErrorBody(error=ErrorDetail(code=exc.code, message=exc.message))
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(), headers=exc.headers)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Render an invalid request body or parameter as an ``INVALID_REQUEST`` error."""
    error = ApiError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "INVALID_REQUEST",
        "Please check your input and try again.",
    )
    return await api_error_handler(request, error)
