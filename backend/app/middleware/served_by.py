"""The ``X-Served-By`` response header: which replica answered."""

from __future__ import annotations

import socket

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The container's hostname: its id in Compose, the pod name in Kubernetes.
HOSTNAME = socket.gethostname()


class ServedByMiddleware:
    """Add ``X-Served-By: <hostname>`` to every HTTP response, streamed ones included."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("X-Served-By", HOSTNAME)
            await send(message)

        await self.app(scope, receive, send_with_header)
