from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, require_workspace_role
from app.db.session import get_db
from app.models.outcomes import OutcomeMonitor, OutcomeMonitorRun
from app.outcomes import service as outcome_service
from app.schemas.intelligence import (
    OutcomeCheckResult,
    OutcomeMonitorCreate,
    OutcomeMonitorRead,
    OutcomeMonitorRunRead,
    OutcomeMonitorUpdate,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/outcome-monitors", tags=["Outcome Monitors"])


def _to_read(m: OutcomeMonitor, workflow_name: str | None = None) -> OutcomeMonitorRead:
    return OutcomeMonitorRead(
        id=m.id,
        workspace_id=m.workspace_id,
        workflow_id=m.workflow_id,
        workflow_name=workflow_name,
        name=m.name,
        description=m.description,
        monitor_type=m.monitor_type,
        configuration=m.configuration,
        expected_result=m.expected_result,
        schedule_seconds=m.schedule_seconds,
        severity=m.severity,
        enabled=m.enabled,
        status=m.status,
        last_checked_at=m.last_checked_at,
        last_success_at=m.last_success_at,
        last_failure_at=m.last_failure_at,
        failure_evidence=m.failure_evidence,
        is_demo=m.is_demo,
        created_at=m.created_at,
    )


@router.get("", response_model=list[OutcomeMonitorRead])
def list_outcome_monitors(
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> list[OutcomeMonitorRead]:
    rows = outcome_service.list_monitors(db, workspace_id=ctx.workspace.id)
    return [_to_read(m, wf_name) for m, wf_name in rows]


@router.post("", response_model=OutcomeMonitorRead, status_code=status.HTTP_201_CREATED)
def create_outcome_monitor(
    body: OutcomeMonitorCreate,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> OutcomeMonitorRead:
    m, wf_name = outcome_service.create_monitor(
        db,
        workspace=ctx.workspace,
        actor_id=ctx.user.id,
        payload=body,
    )
    return _to_read(m, wf_name)


@router.patch("/{monitor_id}", response_model=OutcomeMonitorRead)
def update_outcome_monitor(
    monitor_id: uuid.UUID,
    body: OutcomeMonitorUpdate,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> OutcomeMonitorRead:
    m, wf_name = outcome_service.update_monitor(
        db,
        workspace_id=ctx.workspace.id,
        monitor_id=monitor_id,
        actor_id=ctx.user.id,
        payload=body,
    )
    return _to_read(m, wf_name)


@router.delete("/{monitor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_outcome_monitor(
    monitor_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> Response:
    outcome_service.delete_monitor(
        db,
        workspace_id=ctx.workspace.id,
        monitor_id=monitor_id,
        actor_id=ctx.user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{monitor_id}/enable", response_model=OutcomeMonitorRead)
def enable_outcome_monitor(
    monitor_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> OutcomeMonitorRead:
    m, wf_name = outcome_service.update_monitor(
        db,
        workspace_id=ctx.workspace.id,
        monitor_id=monitor_id,
        actor_id=ctx.user.id,
        payload=OutcomeMonitorUpdate(enabled=True),
    )
    return _to_read(m, wf_name)


@router.post("/{monitor_id}/disable", response_model=OutcomeMonitorRead)
def disable_outcome_monitor(
    monitor_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> OutcomeMonitorRead:
    m, wf_name = outcome_service.update_monitor(
        db,
        workspace_id=ctx.workspace.id,
        monitor_id=monitor_id,
        actor_id=ctx.user.id,
        payload=OutcomeMonitorUpdate(enabled=False),
    )
    return _to_read(m, wf_name)


@router.post("/{monitor_id}/check", response_model=OutcomeCheckResult)
def execute_outcome_monitor_check(
    monitor_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> OutcomeCheckResult:
    monitor = outcome_service.get_monitor_or_404(db, workspace_id=ctx.workspace.id, monitor_id=monitor_id)
    run, incident_id = outcome_service.evaluate_monitor(db, workspace=ctx.workspace, monitor=monitor)
    return OutcomeCheckResult(
        monitor=_to_read(monitor),
        run=OutcomeMonitorRunRead.model_validate(run),
        incident_id=incident_id,
    )


@router.post("/{monitor_id}/confirm", status_code=status.HTTP_201_CREATED)
def confirm_outcome_webhook(
    monitor_id: uuid.UUID,
    external_execution_id: str | None = Query(default=None),
    payload: dict[str, Any] = Body(default_factory=dict),
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    ev = outcome_service.record_webhook_confirmation(
        db,
        workspace_id=ctx.workspace.id,
        monitor_id=monitor_id,
        external_execution_id=external_execution_id,
        payload=payload,
    )
    return {"status": "confirmed", "event_id": str(ev.id)}


@router.get("/{monitor_id}/runs", response_model=list[OutcomeMonitorRunRead])
def list_monitor_runs(
    monitor_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> list[OutcomeMonitorRunRead]:
    outcome_service.get_monitor_or_404(db, workspace_id=ctx.workspace.id, monitor_id=monitor_id)
    runs = list(
        db.scalars(
            select(OutcomeMonitorRun)
            .where(OutcomeMonitorRun.monitor_id == monitor_id)
            .order_by(OutcomeMonitorRun.checked_at.desc())
            .limit(30)
        ).all()
    )
    return [OutcomeMonitorRunRead.model_validate(r) for r in runs]
