from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, require_workspace_role
from app.db.session import get_db
from app.models.monitoring import Execution, ExecutionEvent, Workflow
from app.schemas.identity import PaginatedResponse
from app.schemas.monitoring import ExecutionDetailRead, ExecutionEventRead, ExecutionRead

router = APIRouter(prefix="/workspaces/{workspace_id}/executions", tags=["Executions"])


@router.get("", response_model=PaginatedResponse[ExecutionRead])
def list_executions(
    workflow_id: uuid.UUID | None = Query(default=None),
    execution_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ExecutionRead]:
    stmt = select(Execution).where(Execution.workspace_id == ctx.workspace.id)
    count_stmt = select(func.count(Execution.id)).where(Execution.workspace_id == ctx.workspace.id)

    if workflow_id:
        stmt = stmt.where(Execution.workflow_id == workflow_id)
        count_stmt = count_stmt.where(Execution.workflow_id == workflow_id)
    if execution_status:
        stmt = stmt.where(Execution.status == execution_status)
        count_stmt = count_stmt.where(Execution.status == execution_status)

    total = db.scalar(count_stmt) or 0
    rows = list(db.scalars(stmt.order_by(Execution.started_at.desc()).limit(limit).offset(offset)).all())
    return PaginatedResponse(
        items=[ExecutionRead.model_validate(r) for r in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/{execution_id}", response_model=ExecutionDetailRead)
def get_execution(
    execution_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> ExecutionDetailRead:
    execution = db.scalar(
        select(Execution).where(Execution.id == execution_id, Execution.workspace_id == ctx.workspace.id)
    )
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "EXECUTION_NOT_FOUND", "message": "Execution not found"},
        )
    wf = db.get(Workflow, execution.workflow_id)
    events = list(
        db.scalars(
            select(ExecutionEvent)
            .where(ExecutionEvent.execution_id == execution.id)
            .order_by(ExecutionEvent.event_timestamp.asc())
        ).all()
    )
    base = ExecutionRead.model_validate(execution)
    return ExecutionDetailRead(
        **base.model_dump(),
        workflow_name=wf.name if wf else None,
        events=[ExecutionEventRead.model_validate(e) for e in events],
    )
