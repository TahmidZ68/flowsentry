from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import get_settings
from app.core.extensions import extension_registry


class AuthenticationError(Exception):
    """Raised when JWT or API key authentication fails."""


@lru_cache(maxsize=4)
def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(
        jwks_url,
        cache_keys=True,
        cache_jwk_set=True,
        lifespan=300,
        timeout=10,
    )


def verify_jwt_token(token: str) -> dict[str, Any]:
    """
    Verify an incoming Bearer JWT.

    - In production / supabase mode: validates RS256/ES256 via Supabase JWKS,
      or HS256 via SUPABASE_JWT_SECRET if configured.
    - In local_dev mode (strictly disallowed in production): validates HS256
      tokens signed with LOCAL_DEV_JWT_SECRET.
    """
    settings = get_settings()

    plugin_auth = extension_registry.auth_providers.get(settings.AUTH_MODE)
    if plugin_auth is not None:
        return plugin_auth.verify_token(token)

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Malformed JWT header") from exc

    alg = header.get("alg")

    if settings.AUTH_MODE == "local_dev":
        if settings.ENVIRONMENT == "production":
            raise AuthenticationError("local_dev auth is forbidden in production")
        secret = settings.LOCAL_DEV_JWT_SECRET
        if not secret:
            raise AuthenticationError("LOCAL_DEV_JWT_SECRET is not configured")
        if alg != "HS256":
            raise AuthenticationError("Unsupported algorithm in local_dev mode")
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"Invalid token: {exc}") from exc

    # Supabase Auth verification
    expected_issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1" if settings.SUPABASE_URL else None

    if alg in {"RS256", "ES256"}:
        if not settings.SUPABASE_URL:
            raise AuthenticationError("SUPABASE_URL is not configured for JWKS verification")
        jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
        try:
            signing_key = _get_jwk_client(jwks_url).get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
                issuer=expected_issuer,
                options={"require": ["exp", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"Invalid JWKS-signed token: {exc}") from exc

    if alg == "HS256" and settings.SUPABASE_JWT_SECRET:
        try:
            decode_kwargs: dict[str, Any] = {
                "algorithms": ["HS256"],
                "audience": "authenticated",
                "options": {"require": ["exp", "sub"]},
            }
            if expected_issuer:
                decode_kwargs["issuer"] = expected_issuer
            return jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                **decode_kwargs,
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"Invalid HS256 token: {exc}") from exc

    raise AuthenticationError(f"Unsupported or unconfigured JWT algorithm: {alg}")


def create_local_dev_token(
    *,
    user_id: uuid.UUID,
    email: str,
    name: str | None = None,
    expires_minutes: int = 120,
) -> str:
    """Issue a signed JWT strictly for local_dev / automated test environments."""
    settings = get_settings()
    if settings.ENVIRONMENT == "production" or settings.AUTH_MODE != "local_dev":
        raise AuthenticationError("Local dev tokens are disabled outside local_dev mode")
    if not settings.LOCAL_DEV_JWT_SECRET:
        raise AuthenticationError("LOCAL_DEV_JWT_SECRET is required")

    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
        "user_metadata": {"name": name or email.split("@")[0]},
    }
    return jwt.encode(payload, settings.LOCAL_DEV_JWT_SECRET, algorithm="HS256")


def generate_api_key() -> tuple[str, str, str]:
    """Generate a workspace API key returning (plaintext_key, prefix, sha256_hash)."""
    raw = secrets.token_urlsafe(32)
    full_key = f"fs_live_{raw}"
    prefix = full_key[:14]
    key_hash = hashlib.sha256(full_key.encode("utf-8")).hexdigest()
    return full_key, prefix, key_hash


def hash_secret_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_hashed_secret(raw_value: str, expected_hash: str) -> bool:
    computed = hash_secret_token(raw_value)
    return hmac.compare_digest(computed, expected_hash)
