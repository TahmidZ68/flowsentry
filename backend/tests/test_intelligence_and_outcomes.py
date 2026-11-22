from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from app.intelligence import service as intelligence_service
from app.intelligence.providers import OpenAIProvider
from app.models.identity import Workspace
from app.models.incidents import Incident
from app.models.outcomes import OutcomeMonitor
from app.outcomes import service as outcome_service
from tests.conftest import issue_auth_headers


def _setup(client: TestClient, email: str = "intel@acme.dev") -> tuple[dict[str, str], str, str]:
    headers, _ = issue_auth_headers(client, email, "Intel Engineer")
    ws = client.post("/api/v1/workspaces", json={"name": "Intel WS"}, headers=headers).json()
    ws_id = ws["id"]
    proj_id = client.get(f"/api/v1/workspaces/{ws_id}/projects", headers=headers).json()["items"][0]["id"]
    return headers, ws_id, proj_id


def test_ai_investigation_fallback_and_provider_mock_scenario_5(client: TestClient, db_session) -> None:
    headers, ws_id, proj_id = _setup(client)

    # Trigger an HTTP 429 failure
    ingest = client.post(
        f"/api/v1/workspaces/{ws_id}/executions/ingest",
        json={
            "project_id": proj_id,
            "provider": "n8n",
            "external_workflow_id": "wf-ai-1",
            "workflow_name": "CRM Sync",
            "external_execution_id": "exec-ai-1",
            "status": "failed",
            "started_at": datetime.now(UTC).isoformat(),
            "failed_node": "Create CRM Contact",
            "error_message": "HTTP 429 Too Many Requests",
            "metadata": {"authorization": "Bearer super-secret-should-not-leak"},
        },
        headers=headers,
    )
    assert ingest.status_code == 200
    inc_id = ingest.json()["incident_id"]

    # Scenario 5: When AI provider is unavailable (no API keys configured), deterministic fallback succeeds
    inv_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/incidents/{inc_id}/investigations",
        json={"run_async": False},
        headers=headers,
    )
    assert inv_resp.status_code == 201, inv_resp.text
    inv = inv_resp.json()
    assert inv["provider"] == "deterministic"
    assert inv["analysis_status"] == "completed"
    assert inv["requires_human_review"] is True
    assert "429" in inv["summary"]
    assert any("Create CRM Contact" in e for e in inv["evidence"])

    # Verify secret was sanitized out of evidence passed to AI
    inc_row = db_session.get(Incident, uuid.UUID(inc_id))
    assert inc_row is not None
    sanitized_ev = intelligence_service.build_sanitized_evidence(db_session, incident=inc_row)
    assert "super-secret-should-not-leak" not in json.dumps(sanitized_ev)

    # Also test OpenAIProvider structured JSON parsing via MockTransport & fallback on 503 outage
    def openai_ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "CRM endpoint returned HTTP 429 rate limit.",
                                    "root_cause_hypothesis": "Burst concurrency exceeded CRM quota.",
                                    "confidence": 0.91,
                                    "evidence": ["HTTP 429 observed on Create CRM Contact"],
                                    "possible_causes": ["Concurrent webhook triggers"],
                                    "recommended_actions": ["Add exponential backoff"],
                                    "severity_assessment": "high",
                                    "requires_human_review": True,
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
            },
        )

    provider = OpenAIProvider("test-key", "gpt-4o-mini", transport=httpx.MockTransport(openai_ok))
    result = provider.analyze(sanitized_ev)
    assert result.provider == "openai"
    assert result.output.confidence == 0.91
    assert result.token_usage["total_tokens"] == 200


def test_outcome_monitors_silent_failure_scenario_3(client: TestClient, db_session) -> None:
    headers, ws_id, proj_id = _setup(client, "outcomes@acme.dev")

    # Technical success execution, BUT missing expected CRM contact_id field!
    t = datetime.now(UTC)
    ingest = client.post(
        f"/api/v1/workspaces/{ws_id}/executions/ingest",
        json={
            "project_id": proj_id,
            "provider": "n8n",
            "external_workflow_id": "wf-crm-silent",
            "workflow_name": "Lead to CRM",
            "external_execution_id": "exec-silent-1",
            "status": "success",
            "started_at": t.isoformat(),
            "finished_at": (t + timedelta(seconds=1)).isoformat(),
            "duration_ms": 1000,
            "metadata": {"lead_email": "lead@example.com"},
        },
        headers=headers,
    )
    assert ingest.status_code == 200
    assert ingest.json()["incident_id"] is None
    wf_id = ingest.json()["workflow_id"]

    # 1. Required output fields monitor detects missing metadata.crm_contact_id -> opens SILENT_FAILURE incident!
    m1 = client.post(
        f"/api/v1/workspaces/{ws_id}/outcome-monitors",
        json={
            "workflow_id": wf_id,
            "name": "CRM Contact Created Check",
            "monitor_type": "required_output_fields",
            "configuration": {"required_fields": ["metadata.crm_contact_id"]},
            "expected_result": {"required_fields": ["metadata.crm_contact_id"]},
            "severity": "critical",
        },
        headers=headers,
    )
    assert m1.status_code == 201, m1.text
    m1_id = m1.json()["id"]

    chk1 = client.post(
        f"/api/v1/workspaces/{ws_id}/outcome-monitors/{m1_id}/check",
        headers=headers,
    )
    assert chk1.status_code == 200
    assert chk1.json()["run"]["passed"] is False
    assert chk1.json()["monitor"]["status"] == "failing"
    assert chk1.json()["incident_id"] is not None

    # 2. Expected count monitor passes (1 run in last hour >= min 1)
    m2 = client.post(
        f"/api/v1/workspaces/{ws_id}/outcome-monitors",
        json={
            "workflow_id": wf_id,
            "name": "Hourly Volume Check",
            "monitor_type": "expected_count",
            "configuration": {"window_seconds": 3600, "min_count": 1},
            "expected_result": {"min_count": 1},
        },
        headers=headers,
    ).json()
    chk2 = client.post(
        f"/api/v1/workspaces/{ws_id}/outcome-monitors/{m2['id']}/check",
        headers=headers,
    ).json()
    assert chk2["run"]["passed"] is True

    # 3. External record existence check via MockTransport verifying CRM API response
    m3 = client.post(
        f"/api/v1/workspaces/{ws_id}/outcome-monitors",
        json={
            "workflow_id": wf_id,
            "name": "HubSpot Contact Lookup",
            "monitor_type": "external_record_check",
            "configuration": {"url": "https://93.184.216.34/crm/contacts?email=lead@example.com"},
            "expected_result": {"status_code": 200, "json_path": "results", "min_records": 1},
        },
        headers=headers,
    ).json()

    ws_row = db_session.get(Workspace, uuid.UUID(ws_id))
    m3_row = db_session.get(OutcomeMonitor, uuid.UUID(m3["id"]))
    assert ws_row is not None and m3_row is not None

    empty_crm = httpx.MockTransport(lambda _r: httpx.Response(200, json={"results": []}))
    run_fail, inc_fail = outcome_service.evaluate_monitor(
        db_session, workspace=ws_row, monitor=m3_row, transport=empty_crm
    )
    assert run_fail.passed is False
    assert inc_fail is not None

    valid_crm = httpx.MockTransport(lambda _r: httpx.Response(200, json={"results": [{"id": "c1"}]}))
    run_ok, inc_ok = outcome_service.evaluate_monitor(db_session, workspace=ws_row, monitor=m3_row, transport=valid_crm)
    assert run_ok.passed is True
    assert inc_ok is None


def test_demo_workspace_isolation_and_reset(client: TestClient) -> None:
    headers, prod_ws_id, _ = _setup(client, "demo-owner@acme.dev")

    demo1 = client.post("/api/v1/demo/seed", headers=headers)
    assert demo1.status_code == 201, demo1.text
    demo_ws_id = demo1.json()["id"]
    assert demo1.json()["is_demo"] is True
    assert demo_ws_id != prod_ws_id

    # Production workspace remains completely clean (0 workflows, 0 incidents)
    prod_overview = client.get(f"/api/v1/workspaces/{prod_ws_id}/overview", headers=headers).json()
    assert prod_overview["total_workflows"] == 0
    assert prod_overview["active_incidents"] == 0

    # Demo workspace has seeded workflows, incidents, investigations, and monitor
    demo_overview = client.get(f"/api/v1/workspaces/{demo_ws_id}/overview", headers=headers).json()
    assert demo_overview["total_workflows"] == 2
    assert demo_overview["active_incidents"] == 1

    # Reset demo workspace cleanly
    demo2 = client.post("/api/v1/demo/seed", headers=headers)
    assert demo2.status_code == 201
    assert demo2.json()["id"] != demo_ws_id
