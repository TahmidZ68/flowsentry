from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.ssrf import build_ssrf_safe_transport, validate_outbound_url
from app.integrations.normalizer import (
    classify_error_type,
    normalize_timestamp,
    sanitize_payload,
    sanitize_string,
)
from app.schemas.monitoring import ExecutionStatus, NormalizedExecutionEvent

N8N_STATUS_MAP: dict[str, ExecutionStatus] = {
    "success": "success",
    "error": "failed",
    "crashed": "failed",
    "failed": "failed",
    "running": "running",
    "new": "running",
    "waiting": "waiting",
    "canceled": "canceled",
    "unknown": "unknown",
}


class N8nClientError(Exception):
    """Raised when an n8n API request fails."""


class N8nClient:
    """
    Client for the official n8n Public REST API v1.

    Tested against n8n REST API v1 specifications:
    - Auth header: X-N8N-API-KEY
    - GET /api/v1/workflows (cursor pagination via nextCursor)
    - GET /api/v1/executions (cursor pagination via nextCursor, includeData=true|false)
    """

    def __init__(self, base_url: str, api_key: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = validate_outbound_url(base_url).rstrip("/")
        self.api_key = api_key
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "X-N8N-API-KEY": self.api_key,
        }

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        validate_outbound_url(url)
        try:
            with httpx.Client(
                timeout=10.0,
                follow_redirects=False,
                transport=self._transport or build_ssrf_safe_transport(),
            ) as client:
                response = client.request(method, url, headers=self._headers(), params=params)
        except httpx.HTTPError as exc:
            raise N8nClientError(f"Network error contacting n8n instance: {exc}") from exc

        if response.status_code in {401, 403}:
            raise N8nClientError(f"Authentication failed against n8n API (HTTP {response.status_code})")
        if response.status_code >= 400:
            raise N8nClientError(f"n8n API returned HTTP {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise N8nClientError("n8n API returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise N8nClientError("Unexpected n8n API response shape")
        return data

    def validate_connection(self) -> int:
        """Validate connectivity & API key via GET /api/v1/workflows?limit=1."""
        data = self._request("GET", "/api/v1/workflows", params={"limit": 1})
        items = data.get("data", [])
        return len(items) if isinstance(items, list) else 0

    def list_workflows(self, *, max_pages: int = 10) -> list[dict[str, Any]]:
        workflows: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(max_pages):
            params: dict[str, Any] = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            payload = self._request("GET", "/api/v1/workflows", params=params)
            batch = payload.get("data", [])
            if isinstance(batch, list):
                workflows.extend([item for item in batch if isinstance(item, dict)])
            cursor = payload.get("nextCursor")
            if not cursor:
                break
        return workflows

    def list_executions(
        self,
        *,
        started_after: datetime | None = None,
        cursor: str | None = None,
        include_data: bool = True,
        max_pages: int = 5,
    ) -> tuple[list[dict[str, Any]], str | None]:
        executions: list[dict[str, Any]] = []
        next_cursor = cursor
        for _ in range(max_pages):
            params: dict[str, Any] = {
                "limit": 100,
                "includeData": "true" if include_data else "false",
            }
            if next_cursor:
                params["cursor"] = next_cursor
            if started_after:
                params["startedAfter"] = started_after.astimezone(UTC).isoformat().replace("+00:00", "Z")
            payload = self._request("GET", "/api/v1/executions", params=params)
            batch = payload.get("data", [])
            if isinstance(batch, list):
                executions.extend([item for item in batch if isinstance(item, dict)])
            next_cursor = payload.get("nextCursor")
            if not next_cursor:
                break
        return executions, next_cursor


def parse_n8n_api_execution(
    raw: dict[str, Any],
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    workflow_name: str | None = None,
) -> NormalizedExecutionEvent:
    """Translate an n8n GET /api/v1/executions record into NormalizedExecutionEvent."""
    ext_exec_id = str(raw.get("id") or "")
    ext_wf_id = str(raw.get("workflowId") or (raw.get("workflowData") or {}).get("id") or "unknown")
    resolved_wf_name = workflow_name or (raw.get("workflowData") or {}).get("name")

    raw_status = str(raw.get("status") or "unknown").lower()
    status = N8N_STATUS_MAP.get(raw_status, "unknown")

    started_at = normalize_timestamp(raw.get("startedAt"))
    finished_at = normalize_timestamp(raw.get("stoppedAt"), fallback=None) if raw.get("stoppedAt") else None
    duration_ms = None
    if finished_at is not None:
        duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))

    failed_node: str | None = None
    error_message: str | None = None
    data_block = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    result_data = data_block.get("resultData") if isinstance(data_block.get("resultData"), dict) else {}
    if result_data:
        failed_node = result_data.get("lastNodeExecuted")
        err_obj = result_data.get("error")
        if isinstance(err_obj, dict):
            error_message = err_obj.get("message") or err_obj.get("description")
            if not failed_node and isinstance(err_obj.get("node"), dict):
                failed_node = err_obj["node"].get("name")

    error_type = classify_error_type(error_message) if status == "failed" else None

    metadata = sanitize_payload(
        {
            "mode": raw.get("mode"),
            "retryOf": raw.get("retryOf"),
            "retrySuccessId": raw.get("retrySuccessId"),
            "dataTooLargeToDisplay": raw.get("dataTooLargeToDisplay"),
            "redactionInfo": data_block.get("redactionInfo"),
        }
    )

    return NormalizedExecutionEvent(
        provider="n8n",
        workspace_id=workspace_id,
        project_id=project_id,
        external_workflow_id=ext_wf_id,
        workflow_name=resolved_wf_name,
        external_execution_id=ext_exec_id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        failed_node=sanitize_string(failed_node, 255) if failed_node else None,
        error_type=error_type,
        error_message=sanitize_string(error_message, 2000) if error_message else None,
        metadata=metadata,
    )


def parse_n8n_error_webhook(
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
) -> NormalizedExecutionEvent:
    """
    Parse n8n Error Trigger webhook payload (array or single item).

    Handles instant trigger failures where n8n omits execution.id by generating
    a deterministic fallback id.
    """
    item = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(item, dict):
        raise ValueError("Invalid n8n Error Trigger payload")

    execution_obj = item.get("execution") if isinstance(item.get("execution"), dict) else {}
    workflow_obj = item.get("workflow") if isinstance(item.get("workflow"), dict) else {}

    ext_wf_id = str(workflow_obj.get("id") or item.get("workflowId") or "").strip()
    if not ext_wf_id:
        raise ValueError("Payload missing workflow.id")

    wf_name = workflow_obj.get("name") or item.get("workflowName")
    err_obj = execution_obj.get("error") if isinstance(execution_obj.get("error"), dict) else {}
    error_message = err_obj.get("message") or item.get("errorMessage") or "Workflow execution failed"
    failed_node = execution_obj.get("lastNodeExecuted") or item.get("lastNodeExecuted")

    now = datetime.now(UTC)
    started_at = normalize_timestamp(execution_obj.get("startedAt") or item.get("timestamp"), fallback=now)
    finished_at = normalize_timestamp(execution_obj.get("stoppedAt"), fallback=now)

    raw_exec_id = execution_obj.get("id") or item.get("executionId")
    if raw_exec_id:
        ext_exec_id = str(raw_exec_id)
    else:
        # Fallback for instant unsaved trigger failures that lack execution.id
        bucket = started_at.strftime("%Y%m%d%H%M%S")
        digest = hashlib.sha256(f"{ext_wf_id}:{bucket}:{failed_node or ''}:{error_message}".encode()).hexdigest()[:16]
        ext_exec_id = f"unsaved-{digest}"

    duration_ms = execution_obj.get("durationMs")
    if duration_ms is None and execution_obj.get("startedAt") and execution_obj.get("stoppedAt"):
        duration_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))

    metadata = sanitize_payload(
        {
            "execution_url": execution_obj.get("url"),
            "mode": execution_obj.get("mode"),
            "retryOf": execution_obj.get("retryOf"),
            "stack": err_obj.get("stack"),
            "custom": item.get("metadata") or {},
        }
    )

    return NormalizedExecutionEvent(
        provider="n8n",
        workspace_id=workspace_id,
        project_id=project_id,
        external_workflow_id=ext_wf_id,
        workflow_name=str(wf_name) if wf_name else f"Workflow {ext_wf_id}",
        external_execution_id=ext_exec_id,
        status="failed",
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=int(duration_ms) if isinstance(duration_ms, int | float) else None,
        failed_node=sanitize_string(str(failed_node), 255) if failed_node else None,
        error_type=classify_error_type(str(error_message)),
        error_message=sanitize_string(str(error_message), 2000),
        metadata=metadata,
    )
