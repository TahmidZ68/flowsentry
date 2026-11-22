from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, require_workspace_role
from app.db.session import get_db
from app.notifications import service as notification_service
from app.schemas.identity import PaginatedResponse
from app.schemas.notifications import (
    NotificationPreferenceRead,
    NotificationPreferenceUpsert,
    NotificationRead,
    NotificationTestRequest,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/notifications", tags=["Notifications"])


@router.get("", response_model=PaginatedResponse[NotificationRead])
def list_notifications(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> PaginatedResponse[NotificationRead]:
    rows, total = notification_service.list_notifications(db, workspace_id=ctx.workspace.id, limit=limit, offset=offset)
    return PaginatedResponse(
        items=[NotificationRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/preferences", response_model=list[NotificationPreferenceRead])
def list_preferences(
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> list[NotificationPreferenceRead]:
    prefs = notification_service.list_preferences(db, workspace_id=ctx.workspace.id)
    return [notification_service.to_preference_read(p) for p in prefs]


@router.put("/preferences", response_model=NotificationPreferenceRead)
def upsert_preference(
    body: NotificationPreferenceUpsert,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationPreferenceRead:
    pref = notification_service.upsert_preference(
        db,
        workspace_id=ctx.workspace.id,
        actor_id=ctx.user.id,
        payload=body,
    )
    return notification_service.to_preference_read(pref)


@router.post("/test", response_model=NotificationRead)
def test_delivery(
    body: NotificationTestRequest,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationRead:
    notif = notification_service.send_test_notification(
        db,
        workspace_id=ctx.workspace.id,
        channel=body.channel,
    )
    return NotificationRead.model_validate(notif)


@router.post("/{notification_id}/retry", response_model=NotificationRead)
def retry_notification(
    notification_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> NotificationRead:
    notif = notification_service.retry_failed_notification(
        db,
        workspace_id=ctx.workspace.id,
        notification_id=notification_id,
    )
    return NotificationRead.model_validate(notif)
