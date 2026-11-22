from __future__ import annotations

import hashlib
import re
import statistics
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.identity import Workspace
from app.models.incidents import Incident, IncidentNote, IncidentOccurrence
from app.models.monitoring import Execution, Workflow
from app.models.outcomes import OutcomeMonitor

UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
ISO_TS_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", re.IGNORECASE)
LONG_NUM_PATTERN = re.compile(r"\b\d{4,}\b")


def _ensure_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


@dataclass(frozen=True)
class DetectionOutcome:
    incident: Incident | None
    action: str | None  # "created" | "grouped" | "auto_resolved" | None


def normalize_error_signature(error_message: str | None) -> str:
    if not error_message:
        return "unknown_error"
    sig = error_message.strip().lower()
    sig = UUID_PATTERN.sub("<uuid>", sig)
    sig = ISO_TS_PATTERN.sub("<ts>", sig)
    sig = LONG_NUM_PATTERN.sub("<num>", sig)
    sig = re.sub(r"\s+", " ", sig)
    return sig[:240]


def compute_incident_fingerprint(
    *,
    workspace_id: uuid.UUID,
    workflow_id: uuid.UUID,
    error_type: str | None,
    failed_node: str | None,
    error_message: str | None,
) -> str:
    sig = normalize_error_signature(error_message)
    raw = f"{workspace_id}:{workflow_id}:{(error_type or 'UNKNOWN').upper()}:{(failed_node or '').lower()}:{sig}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def determine_severity(
    *,
    error_type: str | None,
    occurrence_count: int = 1,
    is_performance_anomaly: bool = False,
) -> str:
    if is_performance_anomaly and not error_type:
        return "medium"
    et = (error_type or "").upper()
    if et in {"HTTP_401", "HTTP_403"} or occurrence_count >= 5:
        return "critical"
    if et in {"HTTP_429", "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504", "TIMEOUT", "CONNECTION_ERROR"}:
        return "critical" if occurrence_count >= 3 else "high"
    if occurrence_count >= 3:
        return "high"
    return "high" if et else "medium"


def _detect_performance_anomaly(db: Session, workflow: Workflow, execution: Execution) -> str | None:
    if execution.duration_ms is None:
        return None
    if workflow.max_duration_ms and execution.duration_ms > workflow.max_duration_ms:
        return (
            f"Execution duration {execution.duration_ms}ms exceeded "
            f"configured SLA threshold {workflow.max_duration_ms}ms"
        )

    recent_durations = list(
        db.scalars(
            select(Execution.duration_ms)
            .where(
                Execution.workflow_id == workflow.id,
                Execution.id != execution.id,
                Execution.status == "success",
                Execution.duration_ms.is_not(None),
            )
            .order_by(Execution.started_at.desc())
            .limit(20)
        ).all()
    )
    valid = [d for d in recent_durations if d is not None and d > 0]
    if len(valid) >= 5:
        baseline = statistics.median(valid)
        if baseline > 0 and execution.duration_ms > max(baseline * 3.0, baseline + 2000):
            return f"Execution duration {execution.duration_ms}ms deviated >3x from median baseline ({int(baseline)}ms)"
    return None


def _upsert_incident(
    db: Session,
    *,
    workspace: Workspace,
    workflow: Workflow,
    execution: Execution | None,
    title: str,
    description: str,
    error_type: str | None,
    failed_node: str | None,
    error_message: str | None,
    event_time: datetime,
    is_performance_anomaly: bool = False,
) -> tuple[Incident, str]:
    settings = workspace.settings or {}
    grouping_hours = int(settings.get("grouping_window_hours", 24))
    fingerprint = compute_incident_fingerprint(
        workspace_id=workspace.id,
        workflow_id=workflow.id,
        error_type=error_type,
        failed_node=failed_node,
        error_message=error_message,
    )

    active_statuses = ("open", "acknowledged", "investigating", "reopened")
    existing = db.scalar(
        select(Incident)
        .where(
            Incident.workspace_id == workspace.id,
            Incident.fingerprint == fingerprint,
            Incident.status.in_(active_statuses),
            Incident.grouping_window_expires_at >= event_time,
        )
        .order_by(Incident.last_seen_at.desc())
    )

    if existing is not None:
        existing.occurrence_count += 1
        if _ensure_utc(event_time) > _ensure_utc(existing.last_seen_at):
            existing.last_seen_at = event_time
        existing.grouping_window_expires_at = event_time + timedelta(hours=grouping_hours)
        existing.severity = determine_severity(
            error_type=error_type,
            occurrence_count=existing.occurrence_count,
            is_performance_anomaly=is_performance_anomaly,
        )
        if execution is not None:
            already_linked = db.scalar(
                select(IncidentOccurrence).where(
                    IncidentOccurrence.incident_id == existing.id,
                    IncidentOccurrence.execution_id == execution.id,
                )
            )
            if already_linked is None:
                db.add(IncidentOccurrence(incident_id=existing.id, execution_id=execution.id))
        db.flush()
        return existing, "grouped"

    severity = determine_severity(
        error_type=error_type,
        occurrence_count=1,
        is_performance_anomaly=is_performance_anomaly,
    )
    incident = Incident(
        workspace_id=workspace.id,
        workflow_id=workflow.id,
        title=title[:255],
        description=description,
        severity=severity,
        status="open",
        fingerprint=fingerprint,
        grouping_window_expires_at=event_time + timedelta(hours=grouping_hours),
        first_seen_at=event_time,
        last_seen_at=event_time,
        occurrence_count=1,
        is_demo=workspace.is_demo,
    )
    db.add(incident)
    db.flush()

    if execution is not None:
        db.add(IncidentOccurrence(incident_id=incident.id, execution_id=execution.id))

    db.add(
        IncidentNote(
            incident_id=incident.id,
            workspace_id=workspace.id,
            note_type="system",
            content=f"Incident opened automatically from {error_type or 'detection'} on workflow '{workflow.name}'.",
        )
    )
    db.flush()
    return incident, "created"


def _check_recovery_verification(
    db: Session,
    *,
    workspace: Workspace,
    workflow: Workflow,
    execution: Execution,
) -> Incident | None:
    settings = workspace.settings or {}
    required_successes = int(settings.get("recovery_consecutive_successes", 3))
    if required_successes <= 0:
        return None

    open_incidents = list(
        db.scalars(
            select(Incident).where(
                Incident.workspace_id == workspace.id,
                Incident.workflow_id == workflow.id,
                Incident.status.in_(("open", "acknowledged", "investigating", "reopened")),
            )
        ).all()
    )
    if not open_incidents:
        return None

    # Do not auto-resolve if any enabled outcome monitor for this workflow is failing
    failing_monitor = db.scalar(
        select(OutcomeMonitor.id).where(
            OutcomeMonitor.workflow_id == workflow.id,
            OutcomeMonitor.enabled.is_(True),
            OutcomeMonitor.status == "failing",
        )
    )
    if failing_monitor is not None:
        return None

    resolved_one: Incident | None = None
    for inc in open_incidents:
        recent = list(
            db.scalars(
                select(Execution.status)
                .where(
                    Execution.workflow_id == workflow.id,
                    Execution.started_at >= inc.last_seen_at,
                )
                .order_by(Execution.started_at.desc())
                .limit(required_successes)
            ).all()
        )
        if len(recent) >= required_successes and all(s == "success" for s in recent):
            now = datetime.now(UTC)
            inc.status = "resolved"
            inc.resolved_at = now
            inc.resolution_reason = (
                f"auto_resolved: {required_successes} consecutive healthy executions verified after last failure"
            )
            db.add(
                IncidentNote(
                    incident_id=inc.id,
                    workspace_id=workspace.id,
                    note_type="status_change",
                    content=inc.resolution_reason,
                )
            )
            resolved_one = inc
    db.flush()
    return resolved_one


def evaluate_execution_detection(
    db: Session,
    *,
    workspace: Workspace,
    workflow: Workflow,
    execution: Execution,
) -> DetectionOutcome:
    """Run deterministic failure, anomaly, and recovery verification rules on an execution."""
    event_time = execution.finished_at or execution.started_at
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=UTC)

    if execution.status == "failed":
        err_type = execution.error_type or "EXECUTION_ERROR"
        node_label = f" at node '{execution.failed_node}'" if execution.failed_node else ""
        title = f"{workflow.name}: {err_type}{node_label}"
        desc = execution.error_summary or "Workflow execution reported failure."
        incident, action = _upsert_incident(
            db,
            workspace=workspace,
            workflow=workflow,
            execution=execution,
            title=title,
            description=desc,
            error_type=err_type,
            failed_node=execution.failed_node,
            error_message=execution.error_summary,
            event_time=event_time,
        )
        return DetectionOutcome(incident=incident, action=action)

    if execution.status == "success":
        perf_reason = _detect_performance_anomaly(db, workflow, execution)
        if perf_reason:
            incident, action = _upsert_incident(
                db,
                workspace=workspace,
                workflow=workflow,
                execution=execution,
                title=f"{workflow.name}: Performance anomaly detected",
                description=perf_reason,
                error_type="PERFORMANCE_ANOMALY",
                failed_node=None,
                error_message="Execution duration exceeded threshold",
                event_time=event_time,
                is_performance_anomaly=True,
            )
            return DetectionOutcome(incident=incident, action=action)

        resolved = _check_recovery_verification(db, workspace=workspace, workflow=workflow, execution=execution)
        if resolved is not None:
            return DetectionOutcome(incident=resolved, action="auto_resolved")

    return DetectionOutcome(incident=None, action=None)
