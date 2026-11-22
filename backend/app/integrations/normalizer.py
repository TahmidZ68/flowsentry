from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEYS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "password",
    "passwd",
    "secret",
    "client_secret",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "api_key",
    "apikey",
    "x-api-key",
    "x-n8n-api-key",
    "x-flowsentry-webhook-secret",
    "private_key",
    "ssn",
    "credit_card",
    "card_number",
    "cvv",
}

SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(Basic\s+)[A-Za-z0-9+/]+=*", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
]

HTTP_CODE_PATTERN = re.compile(r"\b(?:HTTP|status(?:\s+code)?)\s*[:=]?\s*([45]\d{2})\b", re.IGNORECASE)
STATUS_CODE_FALLBACK_PATTERN = re.compile(r"\b(401|403|404|408|409|422|429|500|502|503|504)\b")


def sanitize_string(text: str, max_len: int = 2000) -> str:
    cleaned = text
    for pattern in SENSITIVE_VALUE_PATTERNS:
        if pattern.groups >= 1:
            cleaned = pattern.sub(r"\1[REDACTED]", cleaned)
        else:
            cleaned = pattern.sub("[REDACTED]", cleaned)
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "...[truncated]"
    return cleaned


def sanitize_payload(value: Any, *, depth: int = 0, max_depth: int = 6) -> Any:
    """Recursively redact secrets, auth headers, tokens, and excessive payload depth."""
    if depth >= max_depth:
        return "[truncated-depth]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return sanitize_string(value, max_len=1500)
    if isinstance(value, list):
        return [sanitize_payload(item, depth=depth + 1, max_depth=max_depth) for item in value[:50]]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in list(value.items())[:100]:
            key_str = str(k)
            if key_str.lower() in SENSITIVE_KEYS or any(
                frag in key_str.lower()
                for frag in ("password", "secret", "token", "api_key", "apikey", "authorization")
            ):
                result[key_str] = "[REDACTED]"
            else:
                result[key_str] = sanitize_payload(v, depth=depth + 1, max_depth=max_depth)
        return result
    return sanitize_string(str(value), max_len=500)


def normalize_timestamp(value: datetime | str | None, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        iso = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(iso)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    if fallback is not None:
        return fallback
    return datetime.now(UTC)


def classify_error_type(error_message: str | None, explicit_error_type: str | None = None) -> str | None:
    if explicit_error_type and explicit_error_type.strip():
        return explicit_error_type.strip().upper()[:128]
    if not error_message:
        return None

    match = HTTP_CODE_PATTERN.search(error_message) or STATUS_CODE_FALLBACK_PATTERN.search(error_message)
    if match:
        return f"HTTP_{match.group(1)}"

    lower = error_message.lower()
    if "rate limit" in lower or "too many requests" in lower:
        return "HTTP_429"
    if "unauthorized" in lower or "invalid token" in lower or "authentication" in lower:
        return "HTTP_401"
    if "timeout" in lower or "timed out" in lower:
        return "TIMEOUT"
    if "connection refused" in lower or "econnrefused" in lower or "dns" in lower:
        return "CONNECTION_ERROR"
    if "validation" in lower or "schema" in lower or "missing required" in lower:
        return "VALIDATION_ERROR"
    return "EXECUTION_ERROR"
