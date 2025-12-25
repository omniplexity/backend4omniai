import contextvars
import json
import logging
from datetime import datetime

request_id_ctx = contextvars.ContextVar("request_id", default=None)
user_id_ctx = contextvars.ContextVar("user_id", default=None)
path_ctx = contextvars.ContextVar("path", default=None)
method_ctx = contextvars.ContextVar("method", default=None)
client_ip_ctx = contextvars.ContextVar("client_ip", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key in (
            "event",
            "request_id",
            "user_id",
            "path",
            "method",
            "status",
            "latency_ms",
            "client_ip",
            "tool",
            "model",
            "error",
        ):
            if hasattr(record, key):
                value = getattr(record, key)
                if value is not None:
                    payload[key] = value

        if "request_id" not in payload:
            ctx_val = request_id_ctx.get()
            if ctx_val:
                payload["request_id"] = ctx_val

        if "user_id" not in payload:
            ctx_val = user_id_ctx.get()
            if ctx_val is not None:
                payload["user_id"] = ctx_val

        if "path" not in payload:
            ctx_val = path_ctx.get()
            if ctx_val:
                payload["path"] = ctx_val

        if "method" not in payload:
            ctx_val = method_ctx.get()
            if ctx_val:
                payload["method"] = ctx_val

        if "client_ip" not in payload:
            ctx_val = client_ip_ctx.get()
            if ctx_val:
                payload["client_ip"] = ctx_val

        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("omni")
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
