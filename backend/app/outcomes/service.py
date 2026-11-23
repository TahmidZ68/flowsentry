from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.entitlements import get_effective_workspace_limits
from app.core.ssrf import SSRFValidationError, build_ssrf_safe_transport, validate_outbound_url
from app.detection.engine import _ensure_utc, _upsert_incident
from app.models.identity import Workspace
from app.models.incidents import Incident, IncidentNote
from app.models.monitoring import Execution, ExecutionEvent, Workflow
from app.models.outcomes import OutcomeMonitor, OutcomeMonitorRun
from app.schemas.intelligence import OutcomeMonitorCreate, OutcomeMonitorUpdate
from app.services.audit_service import record_audit_log


def _extract_dot_path(data: Any, path: str) -> tuple[bool, Any]:
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return False, None
        else:
            return False, None
    return True, cur


def _evaluate_http_check(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    expected_status: int = 200,
    json_path: str | None = None,
    expected_value: Any = None,
    min_items: int | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[bool, dict[str, Any]]:
    try:
        safe_url = validate_outbound_url(url)
    except SSRFValidationError as exc:
        return False, {"reason": f"SSRF validation blocked URL: {exc}"}

    try:
        with httpx.Client(
            timeout=5.0,
            follow_redirects=False,
            transport=transport or build_ssrf_safe_transport(),
        ) as client:
            resp = client.request(method.upper(), safe_url, headers=headers or {})
    except SSRFValidationError as exc:
        return False, {"reason": f"SSRF validation blocked URL: {exc}"}
    except httpx.HTTPError as exc:
        return False, {"reason": f"Outbound HTTP check failed: {exc}"}

    if len(resp.content) > 262_144:
        return False, {"reason": "Response exceeded 256KB safety limit", "status_code": resp.status_code}

    if resp.status_code != expected_status:
        return False, {
            "reason": f"Expected HTTP {expected_status}, received HTTP {resp.status_code}",
            "status_code": resp.status_code,
        }

    if json_path:
        try:
            body = resp.json()
        except ValueError:
            return False, {"reason": "Expected JSON response for path assertion", "status_code": resp.status_code}

        found, actual = _extract_dot_path(body, json_path)
        if not found:
            return False, {"reason": f"JSON path '{json_path}' missing in response", "status_code": resp.status_code}
        if min_items is not None:
            actual_len = len(actual) if isinstance(actual, list | dict) else (1 if actual else 0)
            if actual_len < min_items:
                return False, {
                    "reason": f"Expected at least {min_items} record(s) at '{json_path}', found {actual_len}",
                    "actual_count": actual_len,
                }
        if expected_value is not None and actual != expected_value:
            return False, {
                "reason": f"Expected '{json_path}' == {expected_value!r}, got {actual!r}",
            }
        if expected_value is None and min_items is None and (actual is None or actual == "" or actual == []):
            return False, {"reason": f"Expected non-empty value at '{json_path}'"}

    return True, {"status_code": resp.status_code, "verified": True}


def get_monitor_or_404(db: Session, *, workspace_id: uuid.UUID, monitor_id: uuid.UUID) -> OutcomeMonitor:
    monitor = db.scalar(
        select(OutcomeMonitor).where(
            OutcomeMonitor.id == monitor_id,
            OutcomeMonitor.workspace_id == workspace_id,
        )
    )
    if monitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MONITOR_NOT_FOUND", "message": "Outcome monitor not found"},
        )
    return monitor


def list_monitors(db: Session, *, workspace_id: uuid.UUID) -> list[tuple[OutcomeMonitor, str]]:
    rows = db.execute(
        select(OutcomeMonitor, Workflow.name)
        .join(Workflow, Workflow.id == OutcomeMonitor.workflow_id)
        .where(OutcomeMonitor.workspace_id == workspace_id)
        .order_by(OutcomeMonitor.created_at.desc())
    ).all()
    return [(r[0], r[1]) for r in rows]


def create_monitor(
    db: Session,
    *,
    workspace: Workspace,
    actor_id: uuid.UUID,
    payload: OutcomeMonitorCreate,
) -> tuple[OutcomeMonitor, str]:
    limits, enforced = get_effective_workspace_limits(workspace.plan)
    current = int(
        db.scalar(select(func.count(OutcomeMonitor.id)).where(OutcomeMonitor.workspace_id == workspace.id)) or 0
    )
    if enforced and not workspace.is_demo and current >= limits.max_outcome_monitors:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PLAN_LIMIT_REACHED",
                "message": (
                    f"Current plan ({limits.display_name}) allows at most "
                    f"{limits.max_outcome_monitors} outcome monitor(s)"
                ),
            },
        )

    workflow = db.scalar(
        select(Workflow).where(Workflow.id == payload.workflow_id, Workflow.workspace_id == workspace.id)
    )
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WORKFLOW_NOT_FOUND", "message": "Workflow not found in workspace"},
        )

    if payload.monitor_type in {"http_endpoint", "external_record_check"}:
        target_url = str(payload.configuration.get("url") or "")
        if not target_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "URL_REQUIRED", "message": "configuration.url is required for HTTP/external checks"},
            )
        try:
            validate_outbound_url(target_url)
        except SSRFValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_URL", "message": str(exc)},
            ) from exc

    monitor = OutcomeMonitor(
        workspace_id=workspace.id,
        workflow_id=workflow.id,
        name=payload.name.strip(),
        description=payload.description,
        monitor_type=payload.monitor_type,
        configuration=payload.configuration,
        expected_result=payload.expected_result,
        schedule_seconds=payload.schedule_seconds,
        severity=payload.severity,
        enabled=payload.enabled,
        is_demo=workspace.is_demo,
    )
    db.add(monitor)
    db.flush()

    record_audit_log(
        db,
        workspace_id=workspace.id,
        user_id=actor_id,
        action="outcome_monitor.created",
        resource_type="outcome_monitor",
        resource_id=monitor.id,
        metadata={"monitor_type": monitor.monitor_type, "workflow_id": str(workflow.id)},
    )
    db.commit()
    db.refresh(monitor)
    return monitor, workflow.name


def update_monitor(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    monitor_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: OutcomeMonitorUpdate,
) -> tuple[OutcomeMonitor, str]:
    monitor = get_monitor_or_404(db, workspace_id=workspace_id, monitor_id=monitor_id)
    if payload.name is not None:
        monitor.name = payload.name.strip()
    if payload.description is not None:
        monitor.description = payload.description
    if payload.configuration is not None:
        if monitor.monitor_type in {"http_endpoint", "external_record_check"} and payload.configuration.get("url"):
            try:
                validate_outbound_url(str(payload.configuration["url"]))
            except SSRFValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "INVALID_URL", "message": str(exc)},
                ) from exc
        monitor.configuration = payload.configuration
    if payload.expected_result is not None:
        monitor.expected_result = payload.expected_result
    if payload.schedule_seconds is not None:
        monitor.schedule_seconds = payload.schedule_seconds
    if payload.severity is not None:
        monitor.severity = payload.severity
    if payload.enabled is not None:
        monitor.enabled = payload.enabled

    record_audit_log(
        db,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="outcome_monitor.updated",
        resource_type="outcome_monitor",
        resource_id=monitor.id,
        metadata={"enabled": monitor.enabled},
    )
    db.commit()
    db.refresh(monitor)
    wf = db.get(Workflow, monitor.workflow_id)
    return monitor, (wf.name if wf else "Unknown Workflow")


def delete_monitor(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    monitor_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    monitor = get_monitor_or_404(db, workspace_id=workspace_id, monitor_id=monitor_id)
    record_audit_log(
        db,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="outcome_monitor.deleted",
        resource_type="outcome_monitor",
        resource_id=monitor.id,
        metadata={"name": monitor.name},
    )
    db.delete(monitor)
    db.commit()


def record_webhook_confirmation(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    monitor_id: uuid.UUID,
    external_execution_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ExecutionEvent:
    monitor = get_monitor_or_404(db, workspace_id=workspace_id, monitor_id=monitor_id)
    stmt = select(Execution).where(
        Execution.workspace_id == workspace_id,
        Execution.workflow_id == monitor.workflow_id,
    )
    if external_execution_id:
        stmt = stmt.where(Execution.external_execution_id == external_execution_id)
    execution = db.scalar(stmt.order_by(Execution.started_at.desc()).limit(1))
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXECUTION_NOT_FOUND", "message": "No matching workflow execution to confirm"},
        )

    ev = ExecutionEvent(
        execution_id=execution.id,
        event_type="outcome.confirmed",
        node_name=monitor.name,
        event_timestamp=datetime.now(UTC),
        event_payload={"monitor_id": str(monitor.id), **(payload or {})},
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def evaluate_monitor(
    db: Session,
    *,
    workspace: Workspace,
    monitor: OutcomeMonitor,
    transport: httpx.BaseTransport | None = None,
) -> tuple[OutcomeMonitorRun, uuid.UUID | None]:
    start_ms = time.monotonic()
    now = datetime.now(UTC)
    cfg = monitor.configuration or {}
    exp = monitor.expected_result or {}

    passed = False
    evidence: dict[str, Any] = {}

    if monitor.monitor_type == "expected_interval":
        max_interval = int(cfg.get("max_interval_seconds", 3600))
        latest = db.scalar(
            select(Execution)
            .where(Execution.workflow_id == monitor.workflow_id)
            .order_by(Execution.started_at.desc())
            .limit(1)
        )
        if latest is None:
            passed = False
            evidence = {"reason": "No executions recorded for workflow yet"}
        else:
            age_seconds = int((now - _ensure_utc(latest.started_at)).total_seconds())
            passed = age_seconds <= max_interval
            evidence = {
                "last_execution_at": latest.started_at.isoformat(),
                "age_seconds": age_seconds,
                "max_interval_seconds": max_interval,
                "reason": None if passed else f"No run in {age_seconds}s (limit {max_interval}s)",
            }

    elif monitor.monitor_type == "expected_count":
        window_seconds = int(cfg.get("window_seconds", 3600))
        min_count = int(exp.get("min_count", cfg.get("min_count", 1)))
        status_filter = cfg.get("status")
        cutoff = now - timedelta(seconds=window_seconds)
        count_stmt = select(func.count(Execution.id)).where(
            Execution.workflow_id == monitor.workflow_id,
            Execution.started_at >= cutoff,
        )
        if status_filter:
            count_stmt = count_stmt.where(Execution.status == status_filter)
        actual_count = int(db.scalar(count_stmt) or 0)
        passed = actual_count >= min_count
        evidence = {
            "actual_count": actual_count,
            "min_count": min_count,
            "window_seconds": window_seconds,
            "reason": None
            if passed
            else f"Observed {actual_count} run(s) in {window_seconds}s (expected >= {min_count})",
        }

    elif monitor.monitor_type == "required_output_fields":
        required_fields = [str(f) for f in (exp.get("required_fields") or cfg.get("required_fields") or [])]
        latest = db.scalar(
            select(Execution)
            .where(Execution.workflow_id == monitor.workflow_id, Execution.status == "success")
            .order_by(Execution.started_at.desc())
            .limit(1)
        )
        if latest is None:
            passed = False
            evidence = {"reason": "No successful execution found to verify output fields"}
        else:
            missing: list[str] = []
            for field_path in required_fields:
                ok, val = _extract_dot_path(latest.normalized_payload or {}, field_path)
                if not ok or val is None or val == "":
                    missing.append(field_path)
            passed = len(missing) == 0
            evidence = {
                "execution_id": str(latest.id),
                "required_fields": required_fields,
                "missing_fields": missing,
                "reason": None if passed else f"Missing required output fields: {', '.join(missing)}",
            }

    elif monitor.monitor_type == "http_endpoint":
        passed, evidence = _evaluate_http_check(
            str(cfg.get("url") or ""),
            method=str(cfg.get("method", "GET")),
            expected_status=int(exp.get("status_code", 200)),
            json_path=exp.get("json_path"),
            expected_value=exp.get("expected_value"),
            transport=transport,
        )

    elif monitor.monitor_type == "external_record_check":
        passed, evidence = _evaluate_http_check(
            str(cfg.get("url") or ""),
            method="GET",
            expected_status=int(exp.get("status_code", 200)),
            json_path=exp.get("json_path"),
            expected_value=exp.get("expected_value"),
            min_items=int(exp.get("min_records", 1)) if exp.get("json_path") else None,
            transport=transport,
        )

    elif monitor.monitor_type == "webhook_confirmation":
        grace_seconds = int(cfg.get("grace_period_seconds", 300))
        latest = db.scalar(
            select(Execution)
            .where(Execution.workflow_id == monitor.workflow_id, Execution.status == "success")
            .order_by(Execution.started_at.desc())
            .limit(1)
        )
        if latest is None:
            passed = True
            evidence = {"reason": "No successful execution awaiting confirmation"}
        else:
            confirmed = db.scalar(
                select(ExecutionEvent.id).where(
                    ExecutionEvent.execution_id == latest.id,
                    ExecutionEvent.event_type == "outcome.confirmed",
                )
            )
            if confirmed is not None:
                passed = True
                evidence = {"execution_id": str(latest.id), "confirmed": True}
            else:
                elapsed = int((now - _ensure_utc(latest.started_at)).total_seconds())
                if elapsed <= grace_seconds:
                    passed = True
                    evidence = {"execution_id": str(latest.id), "awaiting_within_grace": True}
                else:
                    passed = False
                    evidence = {
                        "execution_id": str(latest.id),
                        "elapsed_seconds": elapsed,
                        "grace_period_seconds": grace_seconds,
                        "reason": (
                            f"Confirmation webhook not received within {grace_seconds}s "
                            f"for execution {latest.external_execution_id}"
                        ),
                    }

    duration_ms = max(1, int((time.monotonic() - start_ms) * 1000))
    monitor.last_checked_at = now
    incident_id: uuid.UUID | None = None

    if passed:
        monitor.status = "healthy"
        monitor.last_success_at = now
        monitor.failure_evidence = None
        open_silent = list(
            db.scalars(
                select(Incident).where(
                    Incident.workspace_id == workspace.id,
                    Incident.workflow_id == monitor.workflow_id,
                    Incident.title.endswith(f": Silent failure ({monitor.name})"),
                    Incident.status.in_(("open", "acknowledged", "investigating", "reopened")),
                )
            ).all()
        )
        for inc in open_silent:
            inc.status = "resolved"
            inc.resolved_at = now
            inc.resolution_reason = f"auto_resolved: Outcome monitor '{monitor.name}' verified healthy"
            db.add(
                IncidentNote(
                    incident_id=inc.id,
                    workspace_id=workspace.id,
                    note_type="status_change",
                    content=inc.resolution_reason,
                )
            )
            if not workspace.is_demo:
                from app.notifications.service import dispatch_incident_event

                dispatch_incident_event(
                    db,
                    workspace_id=workspace.id,
                    incident=inc,
                    event_type="incident_resolved",
                )
    else:
        monitor.status = "failing"
        monitor.last_failure_at = now
        monitor.failure_evidence = evidence

        wf = db.get(Workflow, monitor.workflow_id)
        if wf is not None:
            reason_msg = str(evidence.get("reason") or f"Outcome monitor '{monitor.name}' failed")
            incident, _ = _upsert_incident(
                db,
                workspace=workspace,
                workflow=wf,
                execution=None,
                title=f"{wf.name}: Silent failure ({monitor.name})",
                description=reason_msg,
                error_type="SILENT_FAILURE",
                failed_node=monitor.name,
                error_message=reason_msg,
                event_time=now,
            )
            incident.severity = monitor.severity
            incident_id = incident.id
            if not workspace.is_demo:
                from app.notifications.service import dispatch_incident_event

                dispatch_incident_event(db, workspace_id=workspace.id, incident=incident, event_type="outcome_failure")

    run = OutcomeMonitorRun(
        monitor_id=monitor.id,
        workspace_id=workspace.id,
        passed=passed,
        evidence=evidence,
        duration_ms=duration_ms,
        checked_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(monitor)
    db.refresh(run)
    return run, incident_id
