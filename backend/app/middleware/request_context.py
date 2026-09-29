"""Middleware binding per-request context to structlog contextvars.

FastAPILoggingMiddleware — binds trace_id, http_method, http_path for HTTP requests
"""

from __future__ import annotations

import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from structlog.contextvars import bind_contextvars, clear_contextvars


class FastAPILoggingMiddleware(BaseHTTPMiddleware):
    """Bind trace_id, http_method, http_path to structlog contextvars for HTTP requests."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        clear_contextvars()
        bind_contextvars(
            trace_id=uuid.uuid4().hex[:8],
            http_method=request.method,
            http_path=request.url.path,
        )
        try:
            return await call_next(request)
        finally:
            clear_contextvars()
