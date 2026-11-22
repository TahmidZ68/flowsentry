from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.identity import WorkspaceMember
from app.models.incidents import Incident, IncidentNote, IncidentOccurrence
from app.models.monitoring import Execution, Workflow
from app.services.audit_service import record_audit_log


def get_incident_or_404(db: Session, *, workspace_id: uuid.UUID, incident_id: uuid.UUID) -> Incident:
    incident = db.scalar(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.workspace_id == workspace_id,
        )
    )
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "INCIDENT_NOT_FOUND", "message": "Incident not found"},
        )
    return incident


def list_incidents(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    search: str | None = None,
    severity: str | None = None,
    incident_status: str | None = None,
    workflow_id: uuid.UUID | None = None,
    sort_by: str = "last_seen_at",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[Incident, str]], int]:
    stmt = (
        select(Incident, Workflow.name)
        .join(Workflow, Workflow.id == Incident.workflow_id)
        .where(Incident.workspace_id == workspace_id)
    )
    count_stmt = select(func.count(Incident.id)).where(Incident.workspace_id == workspace_id)

    if search and search.strip():
        term = f"%{search.strip()}%"
        cond = or_(Incident.title.ilike(term), Incident.description.ilike(term))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if severity:
        stmt = stmt.where(Incident.severity == severity)
        count_stmt = count_stmt.where(Incident.severity == severity)
    if incident_status:
        stmt = stmt.where(Incident.status == incident_status)
        count_stmt = count_stmt.where(Incident.status == incident_status)
    if workflow_id:
        stmt = stmt.where(Incident.workflow_id == workflow_id)
        count_stmt = count_stmt.where(Incident.workflow_id == workflow_id)

    order_col = Incident.first_seen_at.desc() if sort_by == "first_seen_at" else Incident.last_seen_at.desc()
    total = db.scalar(count_stmt) or 0
    rows = db.execute(stmt.order_by(order_col).limit(limit).offset(offset)).all()
    return [(r[0], r[1]) for r in rows], total


def get_incident_details(
    db: Session, *, workspace_id: uuid.UUID, incident_id: uuid.UUID
) -> tuple[Incident, str, list[IncidentNote], list[Execution]]:
    incident = get_incident_or_404(db, workspace_id=workspace_id, incident_id=incident_id)
    workflow = db.get(Workflow, incident.workflow_id)
    notes = list(
        db.scalars(
            select(IncidentNote).where(IncidentNote.incident_id == incident.id).order_by(IncidentNote.created_at.asc())
        ).all()
    )
    executions = list(
        db.scalars(
            select(Execution)
            .join(IncidentOccurrence, IncidentOccurrence.execution_id == Execution.id)
            .where(IncidentOccurrence.incident_id == incident.id)
            .order_by(Execution.started_at.desc())
            .limit(25)
        ).all()
    )
    return incident, (workflow.name if workflow else "Unknown Workflow"), notes, executions


def transition_incident_status(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    incident_id: uuid.UUID,
    actor_id: uuid.UUID,
    new_status: str,
    resolution_notes: str | None = None,
) -> Incident:
    incident = get_incident_or_404(db, workspace_id=workspace_id, incident_id=incident_id)
    old_status = incident.status
    incident.status = new_status

    if new_status == "resolved":
        incident.resolved_at = datetime.now(UTC)
        incident.resolution_reason = "manual_resolution"
        if resolution_notes:
            incident.resolution_notes = resolution_notes
    elif new_status == "reopened":
        incident.resolved_at = None
        incident.resolution_reason = None

    note_text = f"Status changed from '{old_status}' to '{new_status}'."
    if resolution_notes:
        note_text += f" Notes: {resolution_notes}"

    db.add(
        IncidentNote(
            incident_id=incident.id,
            workspace_id=workspace_id,
            author_id=actor_id,
            note_type="status_change",
            content=note_text,
        )
    )
    record_audit_log(
        db,
        workspace_id=workspace_id,
        user_id=actor_id,
        action=f"incident.{new_status}",
        resource_type="incident",
        resource_id=incident.id,
        metadata={"old_status": old_status, "new_status": new_status},
    )
    db.commit()
    db.refresh(incident)

    if new_status == "resolved" and not incident.is_demo:
        from app.notifications.service import dispatch_incident_event

        dispatch_incident_event(db, workspace_id=workspace_id, incident=incident, event_type="incident_resolved")

    return incident


def assign_incident(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    incident_id: uuid.UUID,
    actor_id: uuid.UUID,
    assignee_user_id: uuid.UUID | None,
) -> Incident:
    incident = get_incident_or_404(db, workspace_id=workspace_id, incident_id=incident_id)
    if assignee_user_id is not None:
        member = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == assignee_user_id,
            )
        )
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_ASSIGNEE", "message": "Assignee must be a member of this workspace"},
            )

    incident.assigned_to_user_id = assignee_user_id
    db.add(
        IncidentNote(
            incident_id=incident.id,
            workspace_id=workspace_id,
            author_id=actor_id,
            note_type="system",
            content=f"Incident assigned to {assignee_user_id}" if assignee_user_id else "Incident unassigned",
        )
    )
    record_audit_log(
        db,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="incident.assigned",
        resource_type="incident",
        resource_id=incident.id,
        metadata={"assigned_to_user_id": str(assignee_user_id) if assignee_user_id else None},
    )
    db.commit()
    db.refresh(incident)
    return incident


def add_incident_note(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    incident_id: uuid.UUID,
    actor_id: uuid.UUID,
    content: str,
) -> IncidentNote:
    incident = get_incident_or_404(db, workspace_id=workspace_id, incident_id=incident_id)
    note = IncidentNote(
        incident_id=incident.id,
        workspace_id=workspace_id,
        author_id=actor_id,
        note_type="comment",
        content=content.strip(),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
