from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

from app.models.incidents import Incident
from app.notifications import service as notification_service
from tests.conftest import issue_auth_headers


def _setup(client: TestClient, email: str = "alerts@acme.dev") -> tuple[dict[str, str], str, str]:
    headers, _ = issue_auth_headers(client, email, "Alert Admin")
    ws = client.post("/api/v1/workspaces", json={"name": "Alert WS"}, headers=headers).json()
    ws_id = ws["id"]
    proj_id = client.get(f"/api/v1/workspaces/{ws_id}/projects", headers=headers).json()["items"][0]["id"]
    return headers, ws_id, proj_id


def test_notification_preferences_mask_urls_and_block_ssrf(client: TestClient) -> None:
    headers, ws_id, _ = _setup(client)

    # SSRF rejected
    bad = client.put(
        f"/api/v1/workspaces/{ws_id}/notifications/preferences",
        json={
            "channel": "slack",
            "enabled": True,
            "slack_webhook_url": "http://127.0.0.1:9000/hook",
        },
        headers=headers,
    )
    assert bad.status_code == 422

    # Valid Slack webhook stored encrypted and masked in response
    ok = client.put(
        f"/api/v1/workspaces/{ws_id}/notifications/preferences",
        json={
            "channel": "slack",
            "enabled": True,
            "slack_webhook_url": "https://93.184.216.34/services/T00/B00/SECRET_TOKEN_XYZ",
            "events": ["critical_incident", "high_incident", "outcome_failure"],
            "min_severity": "high",
            "suppression_minutes": 30,
        },
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["has_config"] is True
    assert "SECRET_TOKEN_XYZ" not in json.dumps(body)
    assert body["masked_target"].endswith("_XYZ")

    # Cross-tenant denied
    other_headers, _ = issue_auth_headers(client, "other@tenant.dev", "Other")
    assert client.get(f"/api/v1/workspaces/{ws_id}/notifications", headers=other_headers).status_code == 403
    assert client.get(f"/api/v1/workspaces/{ws_id}/notifications/preferences", headers=other_headers).status_code == 403


def test_notification_dispatch_suppression_retry_and_email(client: TestClient, db_session) -> None:
    headers, ws_id, proj_id = _setup(client, "dispatch@acme.dev")

    client.put(
        f"/api/v1/workspaces/{ws_id}/notifications/preferences",
        json={
            "channel": "slack",
            "enabled": True,
            "slack_webhook_url": "https://93.184.216.34/services/T00/B00/ABC123",
            "events": ["high_incident", "critical_incident"],
            "min_severity": "high",
            "suppression_minutes": 30,
        },
        headers=headers,
    )

    client.put(
        f"/api/v1/workspaces/{ws_id}/notifications/preferences",
        json={
            "channel": "email",
            "enabled": True,
            "email_recipients": ["oncall@acme.dev"],
            "events": ["high_incident"],
            "min_severity": "high",
            "suppression_minutes": 30,
        },
        headers=headers,
    )

    # Create a workflow & incident via ingestion
    ingest = client.post(
        f"/api/v1/workspaces/{ws_id}/executions/ingest",
        json={
            "project_id": proj_id,
            "provider": "n8n",
            "external_workflow_id": "wf-notif",
            "workflow_name": "Billing Sync",
            "external_execution_id": "exec-notif-1",
            "status": "failed",
            "started_at": datetime.now(UTC).isoformat(),
            "error_message": "HTTP 429 Rate limit",
        },
        headers=headers,
    )
    assert ingest.status_code == 200
    inc_id = uuid.UUID(ingest.json()["incident_id"])
    inc = db_session.get(Incident, inc_id)
    assert inc is not None

    # Test Slack delivery + duplicate suppression with MockTransport
    slack_calls = 0

    def slack_ok(_req: httpx.Request) -> httpx.Response:
        nonlocal slack_calls
        slack_calls += 1
        return httpx.Response(200, text="ok")

    sent_list = notification_service.dispatch_incident_event(
        db_session,
        workspace_id=uuid.UUID(ws_id),
        incident=inc,
        event_type="critical_incident",
        transport=httpx.MockTransport(slack_ok),
    )
    assert len(sent_list) == 1
    assert sent_list[0].status == "sent"
    assert slack_calls == 1

    # Second dispatch within 30 min window is suppressed
    suppressed_list = notification_service.dispatch_incident_event(
        db_session,
        workspace_id=uuid.UUID(ws_id),
        incident=inc,
        event_type="critical_incident",
        transport=httpx.MockTransport(slack_ok),
    )
    assert len(suppressed_list) == 1
    assert suppressed_list[0].status == "suppressed"
    assert slack_calls == 1

    # Test failed Slack delivery & retry
    slack_fail = httpx.MockTransport(lambda _r: httpx.Response(500, text="error"))
    failed_notif = notification_service.send_test_notification(
        db_session,
        workspace_id=uuid.UUID(ws_id),
        channel="slack",
        transport=slack_fail,
    )
    assert failed_notif.status == "failed"
    assert failed_notif.attempt_count == 1

    retried = notification_service.retry_failed_notification(
        db_session,
        workspace_id=uuid.UUID(ws_id),
        notification_id=failed_notif.id,
        transport=httpx.MockTransport(slack_ok),
    )
    assert retried.status == "sent"
    assert retried.attempt_count == 2

    # Delivery ledger API lists history
    hist = client.get(f"/api/v1/workspaces/{ws_id}/notifications", headers=headers)
    assert hist.status_code == 200
    assert hist.json()["total"] >= 3


def test_deliver_email_supports_starttls_and_implicit_ssl(monkeypatch) -> None:
    from types import SimpleNamespace

    events: list[str] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int = 5) -> None:
            events.append(f"smtp:{host}:{port}")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self) -> None:
            events.append("starttls")

        def login(self, user: str, _password: str) -> None:
            events.append(f"login:{user}")

        def send_message(self, msg) -> None:
            events.append(f"send:{msg['To']}")

    class FakeSMTPSSL(FakeSMTP):
        def __init__(self, host: str, port: int, timeout: int = 5) -> None:
            events.append(f"smtp_ssl:{host}:{port}")

    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: SimpleNamespace(
            SMTP_HOST="smtp.example.com",
            SMTP_PORT=587,
            SMTP_USER="mailer",
            SMTP_PASSWORD="pw",
            SMTP_FROM_EMAIL="alerts@flowsentry.example",
            SMTP_USE_TLS=True,
        ),
    )
    notification_service._deliver_email(
        ["oncall@example.com"],
        subject="Test 587",
        body="Body",
        smtp_client_factory=FakeSMTP,
    )
    assert events == ["smtp:smtp.example.com:587", "starttls", "login:mailer", "send:oncall@example.com"]

    events.clear()
    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: SimpleNamespace(
            SMTP_HOST="smtp.example.com",
            SMTP_PORT=465,
            SMTP_USER="mailer",
            SMTP_PASSWORD="pw",
            SMTP_FROM_EMAIL="alerts@flowsentry.example",
            SMTP_USE_TLS=True,
        ),
    )
    monkeypatch.setattr(notification_service.smtplib, "SMTP_SSL", FakeSMTPSSL)
    notification_service._deliver_email(
        ["oncall@example.com"],
        subject="Test 465",
        body="Body",
    )
    assert events == ["smtp_ssl:smtp.example.com:465", "login:mailer", "send:oncall@example.com"]
