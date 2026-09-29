"""Structured logging configuration (structlog + stdlib integration).

Dev mode  → colored, human-readable console output
Prod mode → JSON lines (one object per log event)

All existing ``logging.getLogger(__name__)`` calls are automatically
routed through the structlog processor pipeline — no changes needed
in individual modules.
"""

from __future__ import annotations

import logging
import logging.config

import structlog
from structlog.contextvars import merge_contextvars


def setup_logging(*, debug: bool) -> None:
    """Configure structlog + stdlib logging integration.

    Call once at application startup (before any log calls).
    """
    shared_processors: list[structlog.types.Processor] = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if debug:
        renderer = structlog.dev.ConsoleRenderer(colors=True, pad_level=False)
    else:
        renderer = structlog.processors.JSONRenderer()

    # Configure structlog-native loggers (structlog.get_logger())
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Route ALL stdlib log records through structlog's formatting pipeline
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        renderer,
                    ],
                    "foreign_pre_chain": shared_processors,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "structlog",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "handlers": ["console"],
                "level": "DEBUG" if debug else "INFO",
            },
            "loggers": {
                "httpx": {"level": "WARNING"},
                "httpcore": {"level": "WARNING"},
                "httpx2": {"level": "WARNING"},
                "httpcore2": {"level": "WARNING"},
                "openai": {"level": "WARNING"},
                "qdrant_client": {"level": "WARNING"},
            },
        }
    )
