from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, require_workspace_role
from app.db.session import get_db
from app.incidents import service as incident_service
from app.models.incidents import Incident
from app.models.monitoring import Workflow
from app.schemas.identity import PaginatedResponse
from app.schemas.monitoring import (
    ExecutionRead,
    IncidentAssignRequest,
    IncidentDetailRead,
    IncidentNoteCreate,
    IncidentNoteRead,
    IncidentRead,
    IncidentResolveRequest,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/incidents", tags=["Incidents"])


def _to_read(incident: Incident, workflow_name: str | None) -> IncidentRead:
    return IncidentRead(
        id=incident.id,
        workspace_id=incident.workspace_id,
        workflow_id=incident.workflow_id,
        workflow_name=workflow_name,
        title=incident.title,
        description=incident.description,
        severity=incident.severity,
        status=incident.status,
        fingerprint=incident.fingerprint,
        first_seen_at=incident.first_seen_at,
        last_seen_at=incident.last_seen_at,
        occurrence_count=incident.occurrence_count,
        assigned_to_user_id=incident.assigned_to_user_id,
        resolved_at=incident.resolved_at,
        resolution_reason=incident.resolution_reason,
        resolution_notes=incident.resolution_notes,
        is_demo=incident.is_demo,
        created_at=incident.created_at,
    )


@router.get("", response_model=PaginatedResponse[IncidentRead])
def list_incidents(
    search: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    incident_status: str | None = Query(default=None, alias="status"),
    workflow_id: uuid.UUID | None = Query(default=None),
    sort_by: str = Query(default="last_seen_at"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> PaginatedResponse[IncidentRead]:
    rows, total = incident_service.list_incidents(
        db,
        workspace_id=ctx.workspace.id,
        search=search,
        severity=severity,
        incident_status=incident_status,
        workflow_id=workflow_id,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=[_to_read(inc, wf_name) for inc, wf_name in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=IncidentDetailRead)
def get_incident(
    incident_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> IncidentDetailRead:
    inc, wf_name, notes, executions = incident_service.get_incident_details(
        db, workspace_id=ctx.workspace.id, incident_id=incident_id
    )
    base = _to_read(inc, wf_name)
    return IncidentDetailRead(
        **base.model_dump(),
        notes=[IncidentNoteRead.model_validate(n) for n in notes],
        recent_executions=[ExecutionRead.model_validate(e) for e in executions],
    )


@router.post("/{incident_id}/acknowledge", response_model=IncidentRead)
def acknowledge_incident(
    incident_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> IncidentRead:
    inc = incident_service.transition_incident_status(
        db,
        workspace_id=ctx.workspace.id,
        incident_id=incident_id,
        actor_id=ctx.user.id,
        new_status="acknowledged",
    )
    wf = db.get(Workflow, inc.workflow_id)
    return _to_read(inc, wf.name if wf else None)


@router.post("/{incident_id}/investigate", response_model=IncidentRead)
def investigate_incident(
    incident_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> IncidentRead:
    inc = incident_service.transition_incident_status(
        db,
        workspace_id=ctx.workspace.id,
        incident_id=incident_id,
        actor_id=ctx.user.id,
        new_status="investigating",
    )
    wf = db.get(Workflow, inc.workflow_id)
    return _to_read(inc, wf.name if wf else None)


@router.post("/{incident_id}/resolve", response_model=IncidentRead)
def resolve_incident(
    incident_id: uuid.UUID,
    body: IncidentResolveRequest | None = None,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> IncidentRead:
    inc = incident_service.transition_incident_status(
        db,
        workspace_id=ctx.workspace.id,
        incident_id=incident_id,
        actor_id=ctx.user.id,
        new_status="resolved",
        resolution_notes=body.resolution_notes if body else None,
    )
    wf = db.get(Workflow, inc.workflow_id)
    return _to_read(inc, wf.name if wf else None)


@router.post("/{incident_id}/reopen", response_model=IncidentRead)
def reopen_incident(
    incident_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> IncidentRead:
    inc = incident_service.transition_incident_status(
        db,
        workspace_id=ctx.workspace.id,
        incident_id=incident_id,
        actor_id=ctx.user.id,
        new_status="reopened",
    )
    wf = db.get(Workflow, inc.workflow_id)
    return _to_read(inc, wf.name if wf else None)


@router.post("/{incident_id}/assign", response_model=IncidentRead)
def assign_incident(
    incident_id: uuid.UUID,
    body: IncidentAssignRequest,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> IncidentRead:
    inc = incident_service.assign_incident(
        db,
        workspace_id=ctx.workspace.id,
        incident_id=incident_id,
        actor_id=ctx.user.id,
        assignee_user_id=body.user_id,
    )
    wf = db.get(Workflow, inc.workflow_id)
    return _to_read(inc, wf.name if wf else None)


@router.post("/{incident_id}/notes", response_model=IncidentNoteRead, status_code=status.HTTP_201_CREATED)
def add_note(
    incident_id: uuid.UUID,
    body: IncidentNoteCreate,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> IncidentNoteRead:
    note = incident_service.add_incident_note(
        db,
        workspace_id=ctx.workspace.id,
        incident_id=incident_id,
        actor_id=ctx.user.id,
        content=body.content,
    )
    return IncidentNoteRead.model_validate(note)
