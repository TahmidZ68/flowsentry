from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, require_workspace_role
from app.db.session import get_db
from app.models.identity import Project
from app.models.incidents import Incident
from app.models.monitoring import Execution, Workflow
from app.schemas.identity import PaginatedResponse
from app.schemas.monitoring import WorkflowRead, WorkflowUpdate

router = APIRouter(prefix="/workspaces/{workspace_id}/workflows", tags=["Workflows"])


def _build_workflow_read(db: Session, wf: Workflow) -> WorkflowRead:
    stats = db.execute(
        select(
            func.count(Execution.id),
            func.coalesce(func.sum(case((Execution.status == "failed", 1), else_=0)), 0),
            func.avg(Execution.duration_ms),
            func.max(Execution.started_at),
        ).where(Execution.workflow_id == wf.id)
    ).one()
    exec_count = int(stats[0] or 0)
    failed_count = int(stats[1] or 0)
    avg_dur = float(stats[2]) if stats[2] is not None else None
    last_exec_at = stats[3]

    last_status = db.scalar(
        select(Execution.status).where(Execution.workflow_id == wf.id).order_by(Execution.started_at.desc()).limit(1)
    )
    active_incidents = (
        db.scalar(
            select(func.count(Incident.id)).where(
                Incident.workflow_id == wf.id,
                Incident.status.in_(("open", "acknowledged", "investigating", "reopened")),
            )
        )
        or 0
    )

    failure_rate = round((failed_count / exec_count) * 100.0, 2) if exec_count > 0 else 0.0

    return WorkflowRead(
        id=wf.id,
        workspace_id=wf.workspace_id,
        project_id=wf.project_id,
        integration_id=wf.integration_id,
        external_workflow_id=wf.external_workflow_id,
        name=wf.name,
        description=wf.description,
        enabled=wf.enabled,
        max_duration_ms=wf.max_duration_ms,
        expected_interval_seconds=wf.expected_interval_seconds,
        is_demo=wf.is_demo,
        execution_count=exec_count,
        failed_count=failed_count,
        failure_rate=failure_rate,
        avg_duration_ms=round(avg_dur, 1) if avg_dur is not None else None,
        last_execution_at=last_exec_at,
        last_execution_status=last_status,
        active_incidents_count=int(active_incidents),
        created_at=wf.created_at,
    )


@router.get("", response_model=PaginatedResponse[WorkflowRead])
def list_workflows(
    environment: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> PaginatedResponse[WorkflowRead]:
    stmt = select(Workflow).where(Workflow.workspace_id == ctx.workspace.id)
    count_stmt = select(func.count(Workflow.id)).where(Workflow.workspace_id == ctx.workspace.id)

    if environment and environment != "all":
        stmt = stmt.join(Project, Project.id == Workflow.project_id).where(Project.environment == environment)
        count_stmt = count_stmt.join(Project, Project.id == Workflow.project_id).where(
            Project.environment == environment
        )

    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(Workflow.name.ilike(term))
        count_stmt = count_stmt.where(Workflow.name.ilike(term))

    total = db.scalar(count_stmt) or 0
    rows = list(db.scalars(stmt.order_by(Workflow.created_at.desc()).limit(limit).offset(offset)).all())
    return PaginatedResponse(
        items=[_build_workflow_read(db, wf) for wf in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/{workflow_id}", response_model=WorkflowRead)
def get_workflow(
    workflow_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> WorkflowRead:
    wf = db.scalar(select(Workflow).where(Workflow.id == workflow_id, Workflow.workspace_id == ctx.workspace.id))
    if wf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WORKFLOW_NOT_FOUND", "message": "Workflow not found"},
        )
    return _build_workflow_read(db, wf)


@router.patch("/{workflow_id}", response_model=WorkflowRead)
def update_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowUpdate,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> WorkflowRead:
    wf = db.scalar(select(Workflow).where(Workflow.id == workflow_id, Workflow.workspace_id == ctx.workspace.id))
    if wf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WORKFLOW_NOT_FOUND", "message": "Workflow not found"},
        )
    if body.max_duration_ms is not None:
        wf.max_duration_ms = body.max_duration_ms
    if body.expected_interval_seconds is not None:
        wf.expected_interval_seconds = body.expected_interval_seconds
    if body.enabled is not None:
        wf.enabled = body.enabled
    db.commit()
    db.refresh(wf)
    return _build_workflow_read(db, wf)
