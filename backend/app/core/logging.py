"""
Structured JSON logging with request context.

Provides consistent, machine-readable logs with request IDs for tracing.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variables for request-scoped data
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)
stream_id_ctx: ContextVar[str | None] = ContextVar("stream_id", default=None)


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request context if available
        req_id = request_id_ctx.get()
        if req_id:
            log_data["request_id"] = req_id

        usr_id = user_id_ctx.get()
        if usr_id:
            log_data["user_id"] = usr_id

        stream_id = stream_id_ctx.get()
        if stream_id:
            log_data["stream_id"] = stream_id

        # Add extra fields from record
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        # Add exception info if present (but not full traceback in production)
        if record.exc_info and record.exc_info[1]:
            log_data["error"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]),
            }

        # Add source location for debug
        if record.levelno <= logging.DEBUG:
            log_data["source"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }

        return json.dumps(log_data, default=str)


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that includes context in all log messages."""

    def process(
        self, msg: str, kwargs: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        """Process log message with context data."""
        extra = kwargs.get("extra", {})

        # Add any additional data passed to log calls
        if "data" in kwargs:
            extra["extra_data"] = kwargs.pop("data")
            kwargs["extra"] = extra

        return msg, kwargs


def setup_logging(level: str = "INFO", json_output: bool = True) -> None:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON; if False, output plain text
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> ContextLogger:
    """
    Get a context-aware logger.

    Args:
        name: Logger name (typically __name__)

    Returns:
        ContextLogger instance
    """
    return ContextLogger(logging.getLogger(name), {})
