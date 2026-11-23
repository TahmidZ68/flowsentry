from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import RateLimiter, RateLimitExceeded
from app.core.ssrf import SSRFValidationError, _SSRFSafeSyncBackend
from app.intelligence import service as intelligence_service
from app.intelligence.providers import GeminiProvider, OpenAIProvider
from app.models.identity import UsageRecord, Workspace
from app.models.incidents import Incident
from app.models.monitoring import Workflow
from app.models.outcomes import Notification, OutcomeMonitor
from app.notifications import service as notification_service
from app.outcomes import service as outcome_service
from app.schemas.notifications import NotificationPreferenceUpsert
from tests.conftest import issue_auth_headers


def _bootstrap_workspace(client: TestClient, email: str = "phase11@flowsentry.io") -> tuple[dict[str, str], str, str]:
    headers, _ = issue_auth_headers(client, email, "Phase11 Lead")
    ws = client.post("/api/v1/workspaces", json={"name": "Phase11 Workspace"}, headers=headers).json()
    ws_id = ws["id"]
    projs = client.get(f"/api/v1/workspaces/{ws_id}/projects", headers=headers).json()
    return headers, ws_id, projs["items"][0]["id"]


def test_security_ssrf_dns_rebinding_redirects_and_rate_limiter(client: TestClient) -> None:
    # 1. DNS rebinding / TOCTOU blocked inside _SSRFSafeSyncBackend.connect_tcp
    backend = _SSRFSafeSyncBackend(allow_private_hosts=False)
    rebinding_addr = [(2, 1, 6, "", ("169.254.169.254", 80))]
    with (
        patch("app.core.ssrf.socket.getaddrinfo", return_value=rebinding_addr),
        pytest.raises(SSRFValidationError, match="metadata"),
    ):
        backend.connect_tcp("rebind.attacker.example", 80)

    # 2. HTTP 302 redirect to metadata is NOT followed by outcome http_endpoint monitor
    def redirect_to_metadata(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

    with patch("app.outcomes.service.validate_outbound_url", side_effect=lambda url: url):
        ok, ev = outcome_service._evaluate_http_check(
            "https://93.184.216.34/redirect",
            expected_status=200,
            transport=httpx.MockTransport(redirect_to_metadata),
        )
    assert ok is False
    assert "received HTTP 302" in ev["reason"]

    # 3. Rate limiter enforcement in non-test mode (in-memory fallback when Redis absent)
    limiter = RateLimiter()
    with patch(
        "app.core.rate_limit.get_settings",
        return_value=Settings(
            ENVIRONMENT="staging",
            AUTH_MODE="local_dev",
            ENCRYPTION_KEY="dummy",
            REDIS_URL="redis://127.0.0.1:63999/0",
        ),
    ):
        limiter._redis = None
        limiter.check("rl:test:ip", max_requests=2, window_seconds=60)
        limiter.check("rl:test:ip", max_requests=2, window_seconds=60)
        with pytest.raises(RateLimitExceeded):
            limiter.check("rl:test:ip", max_requests=2, window_seconds=60)


def test_ai_resilience_timeout_ratelimit_invalid_json_retry_and_fallback(
    client: TestClient,
    db_session,
) -> None:
    headers, ws_id, proj_id = _bootstrap_workspace(client, "ai-resilience@flowsentry.io")
    ingest = client.post(
        f"/api/v1/workspaces/{ws_id}/executions/ingest",
        json={
            "project_id": proj_id,
            "provider": "n8n",
            "external_workflow_id": "wf-ai-res",
            "workflow_name": "Invoice Sync",
            "external_execution_id": "exec-ai-res-1",
            "status": "failed",
            "started_at": datetime.now(UTC).isoformat(),
            "failed_node": "Stripe Invoice",
            "error_message": "HTTP 503 Service Unavailable",
        },
        headers=headers,
    )
    assert ingest.status_code == 200
    inc_id = uuid.UUID(ingest.json()["incident_id"])
    ws_row = db_session.get(Workspace, uuid.UUID(ws_id))
    inc_row = db_session.get(Incident, inc_id)
    assert ws_row is not None and inc_row is not None

    # Scenario A: Timeout on attempt 1 -> retry succeeds on attempt 2 (OpenAI)
    attempts = {"count": 0}

    def retry_then_succeed(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ReadTimeout("Simulated read timeout")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "Upstream invoice service returned 503.",
                                    "root_cause_hypothesis": "Temporary upstream outage.",
                                    "confidence": 0.89,
                                    "evidence": ["HTTP 503 observed at Stripe Invoice"],
                                    "possible_causes": ["Upstream maintenance"],
                                    "recommended_actions": ["Enable retry with backoff"],
                                    "severity_assessment": "high",
                                    "requires_human_review": True,
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 110, "completion_tokens": 60, "total_tokens": 170},
            },
        )

    inv1 = intelligence_service.start_investigation(
        db_session,
        workspace=ws_row,
        incident=inc_row,
        actor_id=ws_row.owner_id,
        run_async=False,
    )
    mock_settings = Settings(
        ENVIRONMENT="test",
        AUTH_MODE="local_dev",
        ENCRYPTION_KEY="dummy",
        AI_PROVIDER="openai",
        OPENAI_API_KEY="sk-mock-key",
        OPENAI_MODEL="gpt-4o-mini",
    )
    with patch("app.intelligence.providers.get_settings", return_value=mock_settings):
        res1 = intelligence_service.execute_investigation(
            db_session,
            investigation=inv1,
            workspace=ws_row,
            incident=inc_row,
            transport=httpx.MockTransport(retry_then_succeed),
        )
    assert attempts["count"] == 2
    assert res1.analysis_status == "completed"
    assert res1.provider == "openai"
    assert res1.token_usage["total_tokens"] == 170

    # Verify UsageRecord tracked tokens
    usage_row = db_session.query(UsageRecord).filter(UsageRecord.workspace_id == ws_row.id).one()
    assert usage_row.ai_tokens_used == 170

    # Scenario B: HTTP 429 + Invalid JSON across retries -> deterministic fallback
    def rate_limit_then_invalid_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate_limited"})

    inv2 = intelligence_service.start_investigation(
        db_session,
        workspace=ws_row,
        incident=inc_row,
        actor_id=ws_row.owner_id,
        run_async=False,
    )
    with patch("app.intelligence.providers.get_settings", return_value=mock_settings):
        res2 = intelligence_service.execute_investigation(
            db_session,
            investigation=inv2,
            workspace=ws_row,
            incident=inc_row,
            transport=httpx.MockTransport(rate_limit_then_invalid_json),
        )
    assert res2.analysis_status == "completed_fallback"
    assert res2.provider == "deterministic"
    assert res2.requires_human_review is True
    assert "429" in (res2.error_message or "")

    # Scenario C: GeminiProvider sends key in header (not URL) and rejects invalid JSON
    seen_headers: dict[str, str] = {}
    seen_url: list[str] = []

    def gemini_bad_json(request: httpx.Request) -> httpx.Response:
        seen_url.append(str(request.url))
        seen_headers.update({k.lower(): v for k, v in request.headers.items()})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]},
        )

    gem = GeminiProvider("gem-secret-key", "gemini-2.5-flash", transport=httpx.MockTransport(gemini_bad_json))
    with pytest.raises(Exception, match="Invalid Gemini"):
        gem.analyze({"incident": {"title": "test"}})
    assert "gem-secret-key" not in seen_url[0]
    assert seen_headers.get("x-goog-api-key") == "gem-secret-key"

    # OpenAI invalid JSON raises AIProviderError
    bad_oai_transport = httpx.MockTransport(
        lambda _r: httpx.Response(200, json={"choices": [{"message": {"content": "{"}}]})
    )
    oai = OpenAIProvider(
        "sk-test",
        "gpt-4o-mini",
        transport=bad_oai_transport,
    )
    with pytest.raises(Exception, match="Invalid OpenAI"):
        oai.analyze({"incident": {"title": "test"}})


def test_all_six_outcome_monitors_failure_suppression_recovery_and_notifications(
    client: TestClient,
    db_session,
) -> None:
    headers, ws_id, proj_id = _bootstrap_workspace(client, "monitors-p11@flowsentry.io")
    ws_row = db_session.get(Workspace, uuid.UUID(ws_id))
    assert ws_row is not None

    # Configure Slack notification preference listening for outcome_failure and incident_resolved
    notification_service.upsert_preference(
        db_session,
        workspace_id=ws_row.id,
        actor_id=ws_row.owner_id,
        payload=NotificationPreferenceUpsert(
            channel="slack",
            enabled=True,
            min_severity="medium",
            events=["outcome_failure", "incident_resolved"],
            suppression_minutes=60,
            slack_webhook_url="https://93.184.216.34/slack-hook",
        ),
    )

    # Seed initial old failure -> creates workflow wf-mon-1
    old_t = datetime.now(UTC) - timedelta(hours=3)
    client.post(
        f"/api/v1/workspaces/{ws_id}/executions/ingest",
        json={
            "project_id": proj_id,
            "provider": "n8n",
            "external_workflow_id": "wf-mon-1",
            "workflow_name": "Order Pipeline",
            "external_execution_id": "exec-mon-init",
            "status": "success",
            "started_at": old_t.isoformat(),
            "finished_at": (old_t + timedelta(seconds=1)).isoformat(),
            "duration_ms": 200,
            "metadata": {"invoice_id": "inv_1"},
        },
        headers=headers,
    )
    wf = db_session.query(Workflow).filter(Workflow.workspace_id == ws_row.id).one()

    # 1. expected_interval (fails because latest run is 3h old > 60s, then passes after fresh run)
    m_interval = OutcomeMonitor(
        workspace_id=ws_row.id,
        workflow_id=wf.id,
        name="Interval Check",
        monitor_type="expected_interval",
        severity="high",
        schedule_seconds=60,
        configuration={"max_interval_seconds": 60},
        expected_result={"max_interval_seconds": 60},
    )
    # 2. expected_count (fails because 0 runs in last 60s < 2, then passes after 2 fresh runs)
    m_count = OutcomeMonitor(
        workspace_id=ws_row.id,
        workflow_id=wf.id,
        name="Count Check",
        monitor_type="expected_count",
        severity="high",
        schedule_seconds=60,
        configuration={"window_seconds": 60, "min_count": 2},
        expected_result={"min_count": 2},
    )
    # 3. webhook_confirmation (past grace period 0s on old success -> fails, then passes after confirm)
    m_wh = OutcomeMonitor(
        workspace_id=ws_row.id,
        workflow_id=wf.id,
        name="Webhook Confirm Check",
        monitor_type="webhook_confirmation",
        severity="high",
        schedule_seconds=60,
        configuration={"grace_period_seconds": 0},
        expected_result={},
    )
    # 4. http_endpoint & 5. external_record_check
    m_http = OutcomeMonitor(
        workspace_id=ws_row.id,
        workflow_id=wf.id,
        name="HTTP Check",
        monitor_type="http_endpoint",
        severity="high",
        schedule_seconds=60,
        configuration={"url": "https://93.184.216.34/api/health", "method": "GET"},
        expected_result={"status_code": 200, "json_path": "ok", "expected_value": True},
    )
    m_ext = OutcomeMonitor(
        workspace_id=ws_row.id,
        workflow_id=wf.id,
        name="External Record Check",
        monitor_type="external_record_check",
        severity="high",
        schedule_seconds=60,
        configuration={"url": "https://93.184.216.34/api/records"},
        expected_result={"status_code": 200, "json_path": "items", "min_records": 1},
    )
    # 6. required_output_fields (passes initially because invoice_id is present, fails if missing)
    m_fields = OutcomeMonitor(
        workspace_id=ws_row.id,
        workflow_id=wf.id,
        name="Fields Check",
        monitor_type="required_output_fields",
        severity="high",
        schedule_seconds=60,
        configuration={"required_fields": ["metadata.invoice_id"]},
        expected_result={"required_fields": ["metadata.invoice_id"]},
    )
    db_session.add_all([m_interval, m_count, m_wh, m_http, m_ext, m_fields])
    db_session.commit()

    slack_calls: list[dict] = []

    def fail_then_pass_transport(request: httpx.Request) -> httpx.Response:
        if "slack-hook" in str(request.url):
            slack_calls.append(json.loads(request.content.decode()))
            return httpx.Response(200, text="ok")
        return httpx.Response(503, json={"ok": False, "items": []})

    current_transport = {"fn": fail_then_pass_transport}
    orig_dispatch = notification_service.dispatch_incident_event

    def patched_dispatch(db, **kw):
        kw.setdefault("transport", httpx.MockTransport(current_transport["fn"]))
        return orig_dispatch(db, **kw)

    with patch("app.notifications.service.dispatch_incident_event", side_effect=patched_dispatch):
        for mon in (m_interval, m_count, m_wh, m_http, m_ext):
            run, inc_id = outcome_service.evaluate_monitor(
                db_session,
                workspace=ws_row,
                monitor=mon,
                transport=httpx.MockTransport(fail_then_pass_transport),
            )
            assert run.passed is False
            assert inc_id is not None

        # Duplicate failure within suppression window suppresses duplicate Slack alert
        run_dup, _ = outcome_service.evaluate_monitor(
            db_session,
            workspace=ws_row,
            monitor=m_interval,
            transport=httpx.MockTransport(fail_then_pass_transport),
        )
        assert run_dup.passed is False
        suppressed_count = (
            db_session.query(Notification)
            .filter(Notification.workspace_id == ws_row.id, Notification.status == "suppressed")
            .count()
        )
        assert suppressed_count >= 1

        # Now remediate: confirm webhook + ingest 2 fresh healthy executions + return healthy HTTP JSON
        outcome_service.record_webhook_confirmation(
            db_session,
            workspace_id=ws_row.id,
            monitor_id=m_wh.id,
            external_execution_id="exec-mon-init",
        )
        for i in range(2):
            t_now = datetime.now(UTC)
            client.post(
                f"/api/v1/workspaces/{ws_id}/executions/ingest",
                json={
                    "project_id": proj_id,
                    "provider": "n8n",
                    "external_workflow_id": "wf-mon-1",
                    "workflow_name": "Order Pipeline",
                    "external_execution_id": f"exec-mon-ok-{i}",
                    "status": "success",
                    "started_at": t_now.isoformat(),
                    "finished_at": (t_now + timedelta(seconds=1)).isoformat(),
                    "duration_ms": 180,
                    "metadata": {"invoice_id": f"inv_{i}"},
                },
                headers=headers,
            )
        outcome_service.record_webhook_confirmation(
            db_session,
            workspace_id=ws_row.id,
            monitor_id=m_wh.id,
            external_execution_id="exec-mon-ok-1",
        )

        def healthy_transport(request: httpx.Request) -> httpx.Response:
            if "slack-hook" in str(request.url):
                slack_calls.append(json.loads(request.content.decode()))
                return httpx.Response(200, text="ok")
            if "/records" in str(request.url):
                return httpx.Response(200, json={"items": [{"id": "rec_1"}]})
            return httpx.Response(200, json={"ok": True})

        current_transport["fn"] = healthy_transport

        for mon in (m_interval, m_count, m_wh, m_http, m_ext, m_fields):
            run_ok, _ = outcome_service.evaluate_monitor(
                db_session,
                workspace=ws_row,
                monitor=mon,
                transport=httpx.MockTransport(healthy_transport),
            )
            assert run_ok.passed is True
            assert mon.status == "healthy"

    # Every SILENT_FAILURE incident created above is now auto-resolved + recovery notifications dispatched
    open_silent = (
        db_session.query(Incident)
        .filter(
            Incident.workspace_id == ws_row.id,
            Incident.title.like("%: Silent failure (%"),
            Incident.status != "resolved",
        )
        .count()
    )
    assert open_silent == 0
    resolved_notifs = (
        db_session.query(Notification)
        .filter(
            Notification.workspace_id == ws_row.id,
            Notification.event_type == "incident_resolved",
            Notification.status == "sent",
        )
        .count()
    )
    assert resolved_notifs == 5
