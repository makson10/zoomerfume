"""API errors with a stable JSON body the web chat can show to the customer."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """An error response with the body ``{"error": {"code": ..., "message": ...}}``.

    Args:
        status_code: The HTTP status.
        code: A stable machine-readable code, e.g. ``INVALID_PHONE``.
        message: A short text for the customer.
    """

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """Render an :class:`ApiError` as its JSON body."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
