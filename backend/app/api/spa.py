"""Serve the built web chat from the same origin as the API."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


def mount_web_chat(app: FastAPI, directory: Path = STATIC_DIR) -> None:
    """Serve the built frontend at ``/`` when ``directory`` holds one.

    Routes win over the mount, so call it after the API routers are included.

    Args:
        app: The app to mount the frontend on.
        directory: The frontend build output. The image copies it to ``/app/static``.
    """
    if not (directory / "index.html").is_file():
        logger.info("No web chat build in %s, serving the API only", directory)
        return
    app.mount("/", StaticFiles(directory=directory, html=True), name="web")
