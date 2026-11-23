from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.extensions import ExtensionRegistry
from tests.conftest import issue_auth_headers


def test_community_edition_allows_multi_member_rbac_and_projects(client: TestClient) -> None:
    community_settings = Settings(
        ENVIRONMENT="test",
        EDITION="community",
        ENFORCE_SAAS_PLANS=False,
        SELF_HOSTED_RETENTION_DAYS=120,
        AUTH_MODE="local_dev",
        ENCRYPTION_KEY="dummy",
        LOCAL_DEV_JWT_SECRET="test-local-dev-jwt-secret-at-least-32-chars-long",
    )

    owner_headers, _ = issue_auth_headers(client, "selfhost@agency.dev", "Self Host Owner")
    ws = client.post("/api/v1/workspaces", json={"name": "Self Hosted Agency"}, headers=owner_headers).json()
    ws_id = ws["id"]

    with patch("app.core.entitlements.get_settings", return_value=community_settings):
        # Multiple members beyond free-tier cap (1) succeed cleanly in Community Edition
        m1 = client.post(
            f"/api/v1/workspaces/{ws_id}/members",
            json={"email": "eng1@agency.dev", "role": "admin"},
            headers=owner_headers,
        )
        m2 = client.post(
            f"/api/v1/workspaces/{ws_id}/members",
            json={"email": "viewer1@agency.dev", "role": "viewer"},
            headers=owner_headers,
        )
        assert m1.status_code == 201, m1.text
        assert m2.status_code == 201, m2.text

        # More than 2 projects succeed cleanly in Community Edition
        for idx in range(3):
            proj = client.post(
                f"/api/v1/workspaces/{ws_id}/projects",
                json={"name": f"Client Stack {idx}", "environment": "production"},
                headers=owner_headers,
            )
            assert proj.status_code == 201, proj.text

        with patch("app.services.usage_service.get_settings", return_value=community_settings):
            usage = client.get(f"/api/v1/workspaces/{ws_id}/usage", headers=owner_headers)
        assert usage.status_code == 200
        body = usage.json()
        assert body["edition"] == "community"
        assert body["saas_quotas_enabled"] is False
        assert body["plan"]["name"] == "community"
        assert body["plan"]["retention_days"] == 120
        assert body["members_count"] == 3


def test_capabilities_endpoint_and_extension_registry(client: TestClient) -> None:
    caps = client.get("/api/v1/auth/capabilities")
    assert caps.status_code == 200
    data = caps.json()
    assert "edition" in data
    assert "saas_quotas_enabled" in data
    assert set(["n8n", "custom_webhook"]).issubset(set(data["connectors"]))
    assert set(["slack", "email"]).issubset(set(data["notification_channels"]))

    @dataclass(frozen=True)
    class MockEnterpriseConnector:
        provider_id: str = "make_enterprise"
        display_name: str = "Make Enterprise"
        supports_polling: bool = True

    reg = ExtensionRegistry()
    reg.register_connector(MockEnterpriseConnector())
    assert "make_enterprise" in reg.connectors
