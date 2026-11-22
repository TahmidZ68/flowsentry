from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from app.core.config import Settings
from app.core.encryption import EncryptionError, decrypt_json, encrypt_json, mask_secret
from app.core.security import AuthenticationError, create_local_dev_token, verify_jwt_token
from app.core.ssrf import SSRFValidationError, validate_outbound_url


def test_encryption_roundtrip_and_tamper_detection() -> None:
    payload = {"api_key": "n8n_secret_123", "instance": "example"}
    token = encrypt_json(payload)
    assert "n8n_secret_123" not in token
    assert decrypt_json(token) == payload

    tampered = token[:-10] + ("A" if token[-10] != "A" else "B") + token[-9:]
    with pytest.raises(EncryptionError):
        decrypt_json(tampered)

    assert mask_secret("sk-1234567890abcd") == "************abcd"
    assert mask_secret("abc") == "****"


@pytest.mark.parametrize(
    "blocked_url",
    [
        "http://127.0.0.1:5678/api/v1",
        "http://10.0.0.15/api/v1",
        "http://172.16.0.10/api/v1",
        "http://192.168.1.50/api/v1",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]:8000/",
        "file:///etc/passwd",
        "ftp://93.184.216.34/resource",
        "https://user:pass@93.184.216.34/api",
        "http://localhost:5678",
        "http://metadata.google.internal/computeMetadata/v1/",
    ],
)
def test_ssrf_blocks_unsafe_urls(blocked_url: str) -> None:
    with pytest.raises(SSRFValidationError):
        validate_outbound_url(blocked_url, allow_private_hosts=False)


def test_ssrf_allows_public_ip_and_blocks_metadata_even_in_private_mode() -> None:
    assert (
        validate_outbound_url("https://93.184.216.34/api/v1", allow_private_hosts=False)
        == "https://93.184.216.34/api/v1"
    )
    assert (
        validate_outbound_url("http://127.0.0.1:5678/api/v1", allow_private_hosts=True)
        == "http://127.0.0.1:5678/api/v1"
    )
    with pytest.raises(SSRFValidationError):
        validate_outbound_url("http://169.254.169.254/latest/meta-data/", allow_private_hosts=True)


def test_production_config_forbids_local_dev_auth() -> None:
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            AUTH_MODE="local_dev",
            ENCRYPTION_KEY="dummy",
            DEBUG=False,
        )


def test_jwt_verification_rejects_expired_and_wrong_audience() -> None:
    user_id = uuid.uuid4()
    valid = create_local_dev_token(user_id=user_id, email="owner@flowsentry.io")
    claims = verify_jwt_token(valid)
    assert claims["sub"] == str(user_id)

    expired = create_local_dev_token(user_id=user_id, email="owner@flowsentry.io", expires_minutes=-5)
    with pytest.raises(AuthenticationError):
        verify_jwt_token(expired)

    wrong_aud = jwt.encode(
        {
            "sub": str(user_id),
            "email": "owner@flowsentry.io",
            "aud": "wrong-audience",
            "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
        },
        "test-local-dev-jwt-secret-at-least-32-chars-long",
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        verify_jwt_token(wrong_aud)


def test_supabase_jwks_rs256_verification() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    user_id = str(uuid.uuid4())
    token = jwt.encode(
        {
            "sub": user_id,
            "email": "supabase@example.com",
            "aud": "authenticated",
            "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-kid-1"},
    )

    mock_settings = Settings(
        ENVIRONMENT="staging",
        AUTH_MODE="supabase",
        SUPABASE_URL="https://example.supabase.co",
        ENCRYPTION_KEY="dummy",
    )
    mock_jwk_client = SimpleNamespace(get_signing_key_from_jwt=lambda _t: SimpleNamespace(key=public_key))

    with (
        patch("app.core.security.get_settings", return_value=mock_settings),
        patch("app.core.security._get_jwk_client", return_value=mock_jwk_client),
    ):
        decoded = verify_jwt_token(token)
        assert decoded["sub"] == user_id
        assert decoded["email"] == "supabase@example.com"
