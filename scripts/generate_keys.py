"""Generate cryptographic keys for FlowSentry .env configuration."""

import secrets
from cryptography.fernet import Fernet


def main() -> None:
    fernet_key = Fernet.generate_key().decode("utf-8")
    jwt_secret = secrets.token_urlsafe(48)
    print(f"ENCRYPTION_KEY={fernet_key}")
    print(f"LOCAL_DEV_JWT_SECRET={jwt_secret}")


if __name__ == "__main__":
    main()
