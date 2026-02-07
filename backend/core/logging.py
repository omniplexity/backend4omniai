"""Structured logging configuration for OmniAI."""

import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional
import json

# Context variable for request-scoped data
request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request context if available
        ctx = request_context.get()
        if ctx:
            log_data["request_id"] = ctx.get("request_id")
            log_data["path"] = ctx.get("path")

        # Add extra data if provided
        if hasattr(record, "data") and record.data:
            log_data["data"] = record.data

        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for console output."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",   # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console."""
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        ctx = request_context.get()
        request_id = ctx.get("request_id", "-")[:8] if ctx else "-"

        message = f"{timestamp} | {color}{record.levelname:8}{self.RESET} | {request_id} | {record.name} | {record.getMessage()}"

        if hasattr(record, "data") and record.data:
            message += f" | {record.data}"

        if record.exc_info:
            message += f"\n{self.formatException(record.exc_info)}"

        return message


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that includes request context."""

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Process log message with context."""
        extra = kwargs.get("extra", {})
        if "data" in kwargs:
            extra["data"] = kwargs.pop("data")
        kwargs["extra"] = extra
        return msg, kwargs


_loggers: Dict[str, ContextLogger] = {}


def get_logger(name: str) -> ContextLogger:
    """Get a context-aware logger."""
    if name not in _loggers:
        logger = logging.getLogger(name)
        _loggers[name] = ContextLogger(logger, {})
    return _loggers[name]


def setup_logging(
    level: str = "INFO",
    json_output: bool = False,
    log_file: Optional[str] = None,
) -> None:
    """Configure application logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if json_output:
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console_handler)

    # File handler (always JSON)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)

    # Quiet noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
