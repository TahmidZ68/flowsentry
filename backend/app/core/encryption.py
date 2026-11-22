from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class EncryptionError(Exception):
    """Raised when encryption/decryption fails or configuration is invalid."""


def _get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.ENCRYPTION_KEY.strip()
    if not key:
        raise EncryptionError("ENCRYPTION_KEY is not configured")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise EncryptionError("ENCRYPTION_KEY is invalid Fernet key format") from exc


def encrypt_json(data: dict[str, Any]) -> str:
    """Encrypt a JSON-serializable dict using authenticated Fernet encryption."""
    fernet = _get_fernet()
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return fernet.encrypt(raw).decode("utf-8")


def decrypt_json(token: str) -> dict[str, Any]:
    """Decrypt an encrypted token back to a dict."""
    fernet = _get_fernet()
    try:
        raw = fernet.decrypt(token.encode("utf-8"))
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise EncryptionError("Decrypted payload is not a JSON object")
        return parsed
    except InvalidToken as exc:
        raise EncryptionError("Failed to decrypt credential payload") from exc


def mask_secret(value: str, visible_tail: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible_tail:
        return "****"
    return f"{'*' * min(12, len(value) - visible_tail)}{value[-visible_tail:]}"
