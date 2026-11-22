from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

SENSITIVE_HEADER_KEYS = {
    "authorization",
    "x-n8n-api-key",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-flowsentry-webhook-secret",
}

SENSITIVE_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(\"?(?:password|secret|token|api_key|apikey)\"?\s*[:=]\s*\"?)[^\s\",}]+", re.IGNORECASE),
]


def redact_string(value: str) -> str:
    result = value
    for pattern in SENSITIVE_PATTERNS:
        result = pattern.sub(r"\1[REDACTED]", result)
    return result


def redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for k, v in headers.items():
        if k.lower() in SENSITIVE_HEADER_KEYS:
            sanitized[k] = "[REDACTED]"
        else:
            sanitized[k] = redact_string(str(v))
    return sanitized


class JsonFormatter(logging.Formatter):
    """Structured JSON logger with automatic secret redaction."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_string(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact_string(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
