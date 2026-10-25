"""Per-request logging context."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from structlog.contextvars import bind_contextvars, clear_contextvars


class FastAPILoggingMiddleware(BaseHTTPMiddleware):
    """Add a trace id, the HTTP method and the path to every log line of a request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
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
