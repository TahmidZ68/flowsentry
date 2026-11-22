from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.detection.engine import compute_incident_fingerprint, normalize_error_signature
from app.integrations.n8n import parse_n8n_error_webhook
from app.integrations.normalizer import classify_error_type, sanitize_payload


def test_payload_sanitizer_strips_secrets_and_tokens() -> None:
    raw = {
        "headers": {
            "Authorization": "Bearer secret-jwt-token-xyz",
            "X-N8N-API-KEY": "n8n-live-key",
            "Content-Type": "application/json",
        },
        "nested": {
            "api_key": "123456",
            "password": "hunter2",
            "note": (
                "Failed calling with key sk-abcdef1234567890abcdef and "
                "eyJhbGciOiJIUzI1NiJ9.abc.def and token=sk_live_secret_987654321"
            ),
        },
    }
    sanitized = sanitize_payload(raw)
    assert sanitized["headers"]["Authorization"] == "[REDACTED]"
    assert sanitized["headers"]["X-N8N-API-KEY"] == "[REDACTED]"
    assert sanitized["headers"]["Content-Type"] == "application/json"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert "sk-abcdef" not in sanitized["nested"]["note"]
    assert "eyJhbGciOi" not in sanitized["nested"]["note"]
    assert "sk_live_secret_987654321" not in sanitized["nested"]["note"]


def test_error_classification_variants() -> None:
    assert classify_error_type("HTTP 429 Too Many Requests") == "HTTP_429"
    assert classify_error_type("Request failed with status code 401 unauthorized") == "HTTP_401"
    assert classify_error_type("Upstream returned 500 Internal Server Error") == "HTTP_500"
    assert classify_error_type("Operation timed out after 10000ms") == "TIMEOUT"
    assert classify_error_type("ECONNREFUSED 10.0.0.5:443") == "CONNECTION_ERROR"


def test_n8n_error_webhook_parser_handles_list_and_missing_exec_id() -> None:
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    payload = [
        {
            "execution": {
                "id": "231",
                "url": "https://n8n.example.com/execution/231",
                "error": {"message": "HTTP 429 Rate limit exceeded"},
                "lastNodeExecuted": "Create CRM Contact",
                "mode": "webhook",
            },
            "workflow": {"id": "42", "name": "Lead Capture"},
        }
    ]
    event = parse_n8n_error_webhook(payload, workspace_id=ws_id, project_id=proj_id)
    assert event.external_workflow_id == "42"
    assert event.external_execution_id == "231"
    assert event.error_type == "HTTP_429"
    assert event.failed_node == "Create CRM Contact"

    # Unsaved instant failure without execution.id
    ts = datetime(2026, 11, 22, 12, 0, 0, tzinfo=UTC).isoformat()
    unsaved = {
        "timestamp": ts,
        "execution": {"error": {"message": "Trigger parse error"}, "lastNodeExecuted": "Webhook"},
        "workflow": {"id": "42", "name": "Lead Capture"},
    }
    ev1 = parse_n8n_error_webhook(unsaved, workspace_id=ws_id, project_id=proj_id)
    ev2 = parse_n8n_error_webhook(unsaved, workspace_id=ws_id, project_id=proj_id)
    assert ev1.external_execution_id.startswith("unsaved-")
    assert ev1.external_execution_id == ev2.external_execution_id


def test_fingerprint_normalizes_volatile_tokens() -> None:
    ws_id = uuid.uuid4()
    wf_id = uuid.uuid4()
    fp1 = compute_incident_fingerprint(
        workspace_id=ws_id,
        workflow_id=wf_id,
        error_type="HTTP_429",
        failed_node="HubSpot Upsert",
        error_message="Rate limit for request 550e8400-e29b-41d4-a716-446655440000 at 2026-11-22T12:00:01Z",
    )
    fp2 = compute_incident_fingerprint(
        workspace_id=ws_id,
        workflow_id=wf_id,
        error_type="HTTP_429",
        failed_node="HubSpot Upsert",
        error_message="Rate limit for request 123e4567-e89b-12d3-a456-426614174999 at 2026-11-22T12:05:33Z",
    )
    assert fp1 == fp2
    assert "<uuid>" in normalize_error_signature("Failed id 550e8400-e29b-41d4-a716-446655440000")
