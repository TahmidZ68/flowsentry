from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, require_workspace_role
from app.db.session import get_db
from app.incidents.service import get_incident_or_404
from app.intelligence import service as intelligence_service
from app.models.incidents import AIInvestigation
from app.schemas.identity import PaginatedResponse
from app.schemas.intelligence import AIInvestigationRead, InvestigationStartRequest

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["Investigations"])


def _to_read(inv: AIInvestigation) -> AIInvestigationRead:
    return AIInvestigationRead(
        id=inv.id,
        incident_id=inv.incident_id,
        workspace_id=inv.workspace_id,
        provider=inv.provider,
        model=inv.model,
        analysis_status=inv.analysis_status,
        summary=inv.summary,
        root_cause_hypothesis=inv.root_cause_hypothesis,
        confidence=float(inv.confidence) if inv.confidence is not None else None,
        evidence=inv.evidence or [],
        possible_causes=inv.possible_causes or [],
        recommended_actions=inv.recommended_actions or [],
        severity_assessment=inv.severity_assessment,
        requires_human_review=inv.requires_human_review,
        token_usage=inv.token_usage or {},
        error_message=inv.error_message,
        created_at=inv.created_at,
        completed_at=inv.completed_at,
    )


@router.get("/investigations", response_model=PaginatedResponse[AIInvestigationRead])
def list_investigations(
    incident_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AIInvestigationRead]:
    stmt = select(AIInvestigation).where(AIInvestigation.workspace_id == ctx.workspace.id)
    count_stmt = select(func.count(AIInvestigation.id)).where(AIInvestigation.workspace_id == ctx.workspace.id)
    if incident_id:
        stmt = stmt.where(AIInvestigation.incident_id == incident_id)
        count_stmt = count_stmt.where(AIInvestigation.incident_id == incident_id)

    total = int(db.scalar(count_stmt) or 0)
    rows = list(db.scalars(stmt.order_by(AIInvestigation.created_at.desc()).limit(limit).offset(offset)).all())
    return PaginatedResponse(
        items=[_to_read(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/incidents/{incident_id}/investigations",
    response_model=AIInvestigationRead,
    status_code=status.HTTP_201_CREATED,
)
def start_investigation(
    incident_id: uuid.UUID,
    body: InvestigationStartRequest | None = None,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> AIInvestigationRead:
    incident = get_incident_or_404(db, workspace_id=ctx.workspace.id, incident_id=incident_id)
    inv = intelligence_service.start_investigation(
        db,
        workspace=ctx.workspace,
        incident=incident,
        actor_id=ctx.user.id,
        run_async=body.run_async if body else False,
    )
    return _to_read(inv)


@router.get("/investigations/{investigation_id}", response_model=AIInvestigationRead)
def get_investigation(
    investigation_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> AIInvestigationRead:
    inv = db.scalar(
        select(AIInvestigation).where(
            AIInvestigation.id == investigation_id,
            AIInvestigation.workspace_id == ctx.workspace.id,
        )
    )
    if inv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "INVESTIGATION_NOT_FOUND", "message": "Investigation not found"},
        )
    return _to_read(inv)
