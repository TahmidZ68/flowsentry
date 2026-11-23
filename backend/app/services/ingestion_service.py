from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.entitlements import get_effective_workspace_limits
from app.detection.engine import DetectionOutcome, evaluate_execution_detection
from app.integrations.normalizer import classify_error_type, sanitize_payload, sanitize_string
from app.models.identity import UsageRecord, Workspace
from app.models.monitoring import Execution, ExecutionEvent, Integration, Workflow
from app.schemas.monitoring import NormalizedExecutionEvent
from app.services.usage_service import current_period_month


def _get_or_create_workflow(
    db: Session,
    *,
    workspace: Workspace,
    integration: Integration,
    external_workflow_id: str,
    workflow_name: str | None,
) -> Workflow:
    workflow = db.scalar(
        select(Workflow).where(
            Workflow.integration_id == integration.id,
            Workflow.external_workflow_id == external_workflow_id,
        )
    )
    if workflow is not None:
        if workflow_name and workflow.name != workflow_name:
            workflow.name = workflow_name[:255]
        return workflow

    workflow = Workflow(
        workspace_id=workspace.id,
        project_id=integration.project_id,
        integration_id=integration.id,
        external_workflow_id=external_workflow_id[:255],
        name=(workflow_name or f"Workflow {external_workflow_id}")[:255],
        enabled=True,
        is_demo=workspace.is_demo,
    )
    db.add(workflow)
    db.flush()
    return workflow


def _increment_execution_usage(db: Session, *, workspace: Workspace) -> None:
    period = current_period_month()
    usage = db.scalar(
        select(UsageRecord).where(
            UsageRecord.workspace_id == workspace.id,
            UsageRecord.period_month == period,
        )
    )
    limits, enforced = get_effective_workspace_limits(workspace.plan)
    current_count = usage.executions_count if usage else 0
    if enforced and not workspace.is_demo and current_count >= limits.max_monthly_executions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "EXECUTION_QUOTA_EXCEEDED",
                "message": (
                    f"Monthly execution limit ({limits.max_monthly_executions}) "
                    f"reached for {limits.display_name} plan"
                ),
            },
        )
    if usage is None:
        usage = UsageRecord(
            workspace_id=workspace.id,
            period_month=period,
            executions_count=1,
            ai_investigations_count=0,
            ai_tokens_used=0,
        )
        db.add(usage)
    else:
        usage.executions_count += 1


def ingest_normalized_event(
    db: Session,
    *,
    workspace: Workspace,
    integration: Integration,
    event: NormalizedExecutionEvent,
) -> tuple[Execution, Workflow, bool, DetectionOutcome]:
    """
    Idempotently ingest a NormalizedExecutionEvent into PostgreSQL and run deterministic detection.

    Returns (execution, workflow, deduplicated, detection_outcome).
    """
    workflow = _get_or_create_workflow(
        db,
        workspace=workspace,
        integration=integration,
        external_workflow_id=event.external_workflow_id,
        workflow_name=event.workflow_name,
    )

    existing_exec = db.scalar(
        select(Execution).where(
            Execution.workflow_id == workflow.id,
            Execution.external_execution_id == event.external_execution_id,
        )
    )
    if existing_exec is not None:
        return existing_exec, workflow, True, DetectionOutcome(incident=None, action=None)

    _increment_execution_usage(db, workspace=workspace)

    sanitized_meta = sanitize_payload(event.metadata)
    error_type = event.error_type or (classify_error_type(event.error_message) if event.status == "failed" else None)
    error_summary = sanitize_string(event.error_message, 2000) if event.error_message else None

    started_at = event.started_at.astimezone(UTC) if event.started_at.tzinfo else event.started_at.replace(tzinfo=UTC)
    finished_at = (
        (event.finished_at.astimezone(UTC) if event.finished_at.tzinfo else event.finished_at.replace(tzinfo=UTC))
        if event.finished_at
        else None
    )

    execution = Execution(
        workspace_id=workspace.id,
        workflow_id=workflow.id,
        external_execution_id=event.external_execution_id[:255],
        schema_version=event.schema_version,
        status=event.status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=event.duration_ms,
        failed_node=sanitize_string(event.failed_node, 255) if event.failed_node else None,
        error_type=error_type,
        error_summary=error_summary,
        normalized_payload={
            "schema_version": event.schema_version,
            "provider": event.provider,
            "external_workflow_id": event.external_workflow_id,
            "external_execution_id": event.external_execution_id,
            "metadata": sanitized_meta,
        },
        is_demo=workspace.is_demo,
    )
    db.add(execution)
    db.flush()

    db.add(
        ExecutionEvent(
            execution_id=execution.id,
            event_type="execution.failed" if execution.status == "failed" else f"execution.{execution.status}",
            node_name=execution.failed_node,
            event_timestamp=finished_at or started_at,
            event_payload={
                "error_type": execution.error_type,
                "error_summary": execution.error_summary,
                "duration_ms": execution.duration_ms,
            },
        )
    )

    detection = evaluate_execution_detection(
        db,
        workspace=workspace,
        workflow=workflow,
        execution=execution,
    )
    db.flush()

    if detection.incident is not None and not workspace.is_demo:
        from app.notifications.service import dispatch_incident_event

        event_type: str | None = None
        if detection.action == "created":
            event_type = "critical_incident" if detection.incident.severity == "critical" else "high_incident"
        elif detection.action == "grouped" and detection.incident.occurrence_count >= 2:
            event_type = "repeated_failure"
        elif detection.action == "auto_resolved":
            event_type = "incident_resolved"

        if event_type is not None:
            dispatch_incident_event(db, workspace_id=workspace.id, incident=detection.incident, event_type=event_type)

    return execution, workflow, False, detection


def get_or_create_custom_integration(
    db: Session,
    *,
    workspace: Workspace,
    project_id: uuid.UUID,
) -> Integration:
    existing = db.scalar(
        select(Integration).where(
            Integration.workspace_id == workspace.id,
            Integration.project_id == project_id,
            Integration.provider == "custom_webhook",
            Integration.status != "disconnected",
        )
    )
    if existing is not None:
        return existing

    integration = Integration(
        workspace_id=workspace.id,
        project_id=project_id,
        provider="custom_webhook",
        connection_name="Direct Ingestion API",
        encrypted_credentials="{}",
        polling_enabled=False,
        status="connected",
        last_connected_at=datetime.now(UTC),
    )
    db.add(integration)
    db.flush()
    return integration
