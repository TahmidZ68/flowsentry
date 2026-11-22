from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from app.models.identity import Workspace
from app.services import integration_service
from tests.conftest import issue_auth_headers


def _setup_workspace(client: TestClient, email: str = "ops@acme.dev") -> tuple[dict[str, str], str, str]:
    headers, _ = issue_auth_headers(client, email, "Ops Engineer")
    ws = client.post("/api/v1/workspaces", json={"name": "Ops Workspace"}, headers=headers).json()
    ws_id = ws["id"]
    projs = client.get(f"/api/v1/workspaces/{ws_id}/projects", headers=headers).json()
    project_id = projs["items"][0]["id"]
    return headers, ws_id, project_id


def test_n8n_integration_validation_and_sync_with_mock_transport(client: TestClient, db_session) -> None:
    headers, ws_id, project_id = _setup_workspace(client)

    # SSRF check rejects private/metadata URL
    bad_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/integrations",
        json={
            "project_id": project_id,
            "provider": "n8n",
            "connection_name": "Metadata SSRF",
            "base_url": "http://169.254.169.254/latest",
            "api_key": "secret",
        },
        headers=headers,
    )
    assert bad_resp.status_code == 422

    # Create valid n8n integration (using public IP literal to avoid DNS in sandbox)
    create_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/integrations",
        json={
            "project_id": project_id,
            "provider": "n8n",
            "connection_name": "Prod n8n",
            "base_url": "https://93.184.216.34",
            "api_key": "n8n_super_secret_key",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    integration_id = create_resp.json()["integration"]["id"]
    assert "n8n_super_secret_key" not in json.dumps(create_resp.json())

    # Mock n8n REST API v1 responses (paginated workflows + executions)
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-N8N-API-KEY") == "n8n_super_secret_key"
        if request.url.path == "/api/v1/workflows":
            if request.url.params.get("cursor") == "page2":
                return httpx.Response(
                    200,
                    json={
                        "data": [{"id": "wf-2", "name": "Invoice Dispatch", "active": True}],
                        "nextCursor": None,
                    },
                )
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "wf-1", "name": "Lead Sync", "active": True}],
                    "nextCursor": "page2",
                },
            )
        if request.url.path == "/api/v1/executions":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "exec-101",
                            "workflowId": "wf-1",
                            "status": "error",
                            "startedAt": "2026-11-22T10:00:00Z",
                            "stoppedAt": "2026-11-22T10:00:02Z",
                            "mode": "webhook",
                            "data": {
                                "resultData": {
                                    "lastNodeExecuted": "HubSpot Contact",
                                    "error": {"message": "HTTP 429 Rate limit exceeded"},
                                }
                            },
                        },
                        {
                            "id": "exec-102",
                            "workflowId": "wf-2",
                            "status": "success",
                            "startedAt": "2026-11-22T10:05:00Z",
                            "stoppedAt": "2026-11-22T10:05:01Z",
                            "mode": "trigger",
                        },
                    ],
                    "nextCursor": None,
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    ws_row = db_session.get(Workspace, uuid.UUID(ws_id))
    assert ws_row is not None

    val = integration_service.validate_n8n_integration(
        db_session,
        workspace_id=ws_row.id,
        integration_id=uuid.UUID(integration_id),
        actor_id=ws_row.owner_id,
        transport=transport,
    )
    assert val.ok is True
    assert val.workflows_accessible == 1

    sync_res = integration_service.sync_n8n_integration(
        db_session,
        workspace=ws_row,
        integration_id=uuid.UUID(integration_id),
        actor_id=ws_row.owner_id,
        transport=transport,
    )
    assert sync_res.workflows_synced == 2
    assert sync_res.executions_ingested == 2
    assert sync_res.incidents_created == 1

    # Syncing same executions again deduplicates
    sync_again = integration_service.sync_n8n_integration(
        db_session,
        workspace=ws_row,
        integration_id=uuid.UUID(integration_id),
        actor_id=ws_row.owner_id,
        transport=transport,
    )
    assert sync_again.executions_ingested == 0
    assert sync_again.executions_deduplicated == 2

    # Disconnect scrubs credentials
    del_resp = client.delete(
        f"/api/v1/workspaces/{ws_id}/integrations/{integration_id}",
        headers=headers,
    )
    assert del_resp.status_code == 204
    listed = client.get(f"/api/v1/workspaces/{ws_id}/integrations", headers=headers).json()
    assert listed[0]["status"] == "disconnected"
    assert listed[0]["has_credentials"] is False


def test_scenarios_1_2_6_7_webhook_grouping_recovery_and_dedup(client: TestClient) -> None:
    headers, ws_id, project_id = _setup_workspace(client, "sre@acme.dev")

    created = client.post(
        f"/api/v1/workspaces/{ws_id}/integrations",
        json={
            "project_id": project_id,
            "provider": "custom_webhook",
            "connection_name": "n8n Error Webhook",
        },
        headers=headers,
    ).json()
    integration_id = created["integration"]["id"]
    webhook_secret = created["webhook_secret"]

    # Wrong secret rejected
    bad_wh = client.post(
        f"/api/v1/ingest/webhooks/n8n/{integration_id}",
        json={"workflow": {"id": "wf-9", "name": "CRM Sync"}, "execution": {"id": "e1"}},
        headers={"X-FlowSentry-Webhook-Secret": "wrong-secret"},
    )
    assert bad_wh.status_code == 401

    # Scenario 1: HTTP 429 webhook creates incident
    base_time = datetime(2026, 11, 22, 12, 0, 0, tzinfo=UTC)
    wh_payload_1 = {
        "execution": {
            "id": "exec-901",
            "startedAt": base_time.isoformat(),
            "stoppedAt": (base_time + timedelta(seconds=2)).isoformat(),
            "lastNodeExecuted": "Create CRM Contact",
            "error": {"message": "HTTP 429 Rate limit exceeded"},
        },
        "workflow": {"id": "wf-9", "name": "CRM Sync"},
    }
    r1 = client.post(
        f"/api/v1/ingest/webhooks/n8n/{integration_id}",
        json=wh_payload_1,
        headers={"X-FlowSentry-Webhook-Secret": webhook_secret},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["deduplicated"] is False
    assert r1.json()["incident_action"] == "created"
    inc_id = r1.json()["incident_id"]
    wf_id = r1.json()["workflow_id"]

    # Scenario 7: Duplicate delivery of exec-901 does not create duplicate execution or bump count
    r1_dup = client.post(
        f"/api/v1/ingest/webhooks/n8n/{integration_id}",
        json=wh_payload_1,
        headers={"X-FlowSentry-Webhook-Secret": webhook_secret},
    )
    assert r1_dup.status_code == 200
    assert r1_dup.json()["deduplicated"] is True

    # Scenario 2: Two more HTTP 429 failures group into same incident & escalate severity
    for idx, exec_id in enumerate(["exec-902", "exec-903"], start=1):
        t = base_time + timedelta(minutes=idx * 5)
        res = client.post(
            f"/api/v1/ingest/webhooks/n8n/{integration_id}",
            json={
                "execution": {
                    "id": exec_id,
                    "startedAt": t.isoformat(),
                    "stoppedAt": (t + timedelta(seconds=1)).isoformat(),
                    "lastNodeExecuted": "Create CRM Contact",
                    "error": {"message": "HTTP 429 Rate limit exceeded"},
                },
                "workflow": {"id": "wf-9", "name": "CRM Sync"},
            },
            headers={"X-FlowSentry-Webhook-Secret": webhook_secret},
        )
        assert res.status_code == 200
        assert res.json()["incident_id"] == inc_id
        assert res.json()["incident_action"] == "grouped"

    inc_detail = client.get(f"/api/v1/workspaces/{ws_id}/incidents/{inc_id}", headers=headers).json()
    assert inc_detail["occurrence_count"] == 3
    assert inc_detail["severity"] == "critical"

    # Incident lifecycle: acknowledge, add note
    ack = client.post(f"/api/v1/workspaces/{ws_id}/incidents/{inc_id}/acknowledge", headers=headers)
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"

    note = client.post(
        f"/api/v1/workspaces/{ws_id}/incidents/{inc_id}/notes",
        json={"content": "Investigating CRM rate limit quota"},
        headers=headers,
    )
    assert note.status_code == 201

    # Scenario 6: 3 consecutive healthy executions auto-resolve incident
    for idx in range(1, 4):
        t = base_time + timedelta(minutes=30 + idx)
        ok_resp = client.post(
            f"/api/v1/workspaces/{ws_id}/executions/ingest",
            json={
                "project_id": project_id,
                "provider": "n8n",
                "external_workflow_id": "wf-9",
                "workflow_name": "CRM Sync",
                "external_execution_id": f"exec-ok-{idx}",
                "status": "success",
                "started_at": t.isoformat(),
                "finished_at": (t + timedelta(seconds=1)).isoformat(),
                "duration_ms": 950,
            },
            headers=headers,
        )
        # Note: custom_webhook integration created above vs direct ingest custom_webhook:
        # Both map to custom_webhook integration if same project_id!
        assert ok_resp.status_code == 200

    inc_after = client.get(f"/api/v1/workspaces/{ws_id}/incidents/{inc_id}", headers=headers).json()
    assert inc_after["status"] == "resolved"
    assert "auto_resolved" in inc_after["resolution_reason"]

    # Overview & workflows endpoints return real counts
    overview = client.get(f"/api/v1/workspaces/{ws_id}/overview", headers=headers).json()
    assert overview["total_executions"] == 6
    assert overview["successful_executions"] == 3
    assert overview["failed_executions"] == 3
    assert overview["active_incidents"] == 0

    wf_detail = client.get(f"/api/v1/workspaces/{ws_id}/workflows/{wf_id}", headers=headers).json()
    assert wf_detail["execution_count"] == 6
    assert wf_detail["failed_count"] == 3
    assert wf_detail["failure_rate"] == 50.0

    # Cross-tenant check for User B
    user_b_headers, _ = issue_auth_headers(client, "intruder@other.dev", "Intruder")
    assert client.get(f"/api/v1/workspaces/{ws_id}/incidents", headers=user_b_headers).status_code == 403
    assert client.get(f"/api/v1/workspaces/{ws_id}/workflows", headers=user_b_headers).status_code == 403
    assert client.get(f"/api/v1/workspaces/{ws_id}/executions", headers=user_b_headers).status_code == 403
    assert client.get(f"/api/v1/workspaces/{ws_id}/overview", headers=user_b_headers).status_code == 403


def test_phase6_api_key_ingest_webhook_size_limit_and_request_id(client: TestClient) -> None:
    headers, ws_id, project_id = _setup_workspace(client, "apikey-owner@acme.dev")

    # Security headers & X-Request-ID propagation
    health_resp = client.get("/health", headers={"X-Request-ID": "req-phase6-123"})
    assert health_resp.status_code == 200
    assert health_resp.headers.get("x-request-id") == "req-phase6-123"
    assert health_resp.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=()"

    # Create workspace API key
    key_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/api-keys",
        json={"name": "CI Ingest Key", "scopes": ["ingest:write"]},
        headers=headers,
    )
    assert key_resp.status_code == 201, key_resp.text
    key_id = key_resp.json()["api_key"]["id"]
    plaintext_key = key_resp.json()["plaintext_key"]

    base_time = datetime(2026, 11, 22, 14, 0, 0, tzinfo=UTC)
    ingest_payload = {
        "project_id": project_id,
        "provider": "custom_sdk",
        "external_workflow_id": "wf-api-1",
        "workflow_name": "API Key Workflow",
        "external_execution_id": "exec-api-1",
        "status": "failed",
        "started_at": base_time.isoformat(),
        "finished_at": (base_time + timedelta(seconds=1)).isoformat(),
        "duration_ms": 1000,
        "failed_node": "Sync Node",
        "error_message": "HTTP 502 Bad Gateway",
    }

    # Valid X-API-Key succeeds without JWT Bearer token
    ok_ingest = client.post(
        f"/api/v1/workspaces/{ws_id}/executions/ingest",
        json=ingest_payload,
        headers={"X-API-Key": plaintext_key},
    )
    assert ok_ingest.status_code == 200, ok_ingest.text
    assert ok_ingest.json()["incident_action"] == "created"

    # Invalid API key rejected
    bad_ingest = client.post(
        f"/api/v1/workspaces/{ws_id}/executions/ingest",
        json={**ingest_payload, "external_execution_id": "exec-api-2"},
        headers={"X-API-Key": "fs_live_invalid"},
    )
    assert bad_ingest.status_code == 401

    # Revoked API key rejected
    revoke = client.delete(f"/api/v1/workspaces/{ws_id}/api-keys/{key_id}", headers=headers)
    assert revoke.status_code == 204
    revoked_ingest = client.post(
        f"/api/v1/workspaces/{ws_id}/executions/ingest",
        json={**ingest_payload, "external_execution_id": "exec-api-3"},
        headers={"X-API-Key": plaintext_key},
    )
    assert revoked_ingest.status_code == 401

    # Oversized webhook payload (>1 MB) rejected with 413
    wh_created = client.post(
        f"/api/v1/workspaces/{ws_id}/integrations",
        json={"project_id": project_id, "provider": "custom_webhook", "connection_name": "Size Limit WH"},
        headers=headers,
    ).json()
    oversized_body = json.dumps(
        {
            "workflow": {"id": "wf-big", "name": "Big"},
            "execution": {"id": "exec-big", "blob": "A" * 1_100_000},
        }
    )
    big_resp = client.post(
        f"/api/v1/ingest/webhooks/n8n/{wh_created['integration']['id']}",
        content=oversized_body,
        headers={
            "Content-Type": "application/json",
            "X-FlowSentry-Webhook-Secret": wh_created["webhook_secret"],
        },
    )
    assert big_resp.status_code == 413
