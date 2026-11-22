from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment before importing app modules
os.environ["ENVIRONMENT"] = "test"
os.environ["AUTH_MODE"] = "local_dev"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode("utf-8")
os.environ["LOCAL_DEV_JWT_SECRET"] = "test-local-dev-jwt-secret-at-least-32-chars-long"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

import app.models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def issue_auth_headers(client: TestClient, email: str, name: str = "Test User") -> tuple[dict[str, str], str]:
    resp = client.post("/api/v1/auth/dev-token", json={"email": email, "name": name})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return {"Authorization": f"Bearer {data['access_token']}"}, data["user"]["id"]


def random_uuid() -> str:
    return str(uuid.uuid4())
