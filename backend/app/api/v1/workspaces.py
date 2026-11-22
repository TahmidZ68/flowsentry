from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, get_current_user, require_workspace_role
from app.db.session import get_db
from app.models.identity import AuditLog, User
from app.schemas.identity import (
    APIKeyCreate,
    APIKeyCreateResponse,
    APIKeyRead,
    AuditLogRead,
    PaginatedResponse,
    UsageSummaryRead,
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberRead,
    WorkspaceMemberUpdate,
    WorkspaceRead,
    WorkspaceUpdate,
)
from app.services import api_key_service, usage_service, workspace_service

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.get("", response_model=list[WorkspaceRead])
def list_workspaces(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceRead]:
    rows = workspace_service.list_user_workspaces(db, user_id=current_user.id)
    return [
        WorkspaceRead(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            owner_id=ws.owner_id,
            plan=ws.plan,
            is_demo=ws.is_demo,
            settings=ws.settings,
            role=role,  # type: ignore[arg-type]
            created_at=ws.created_at,
        )
        for ws, role in rows
    ]


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceRead:
    ws, member = workspace_service.create_workspace(
        db,
        owner=current_user,
        name=body.name,
        slug=body.slug,
    )
    return WorkspaceRead(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        owner_id=ws.owner_id,
        plan=ws.plan,
        is_demo=ws.is_demo,
        settings=ws.settings,
        role=member.role,  # type: ignore[arg-type]
        created_at=ws.created_at,
    )


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
) -> WorkspaceRead:
    ws = ctx.workspace
    return WorkspaceRead(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        owner_id=ws.owner_id,
        plan=ws.plan,
        is_demo=ws.is_demo,
        settings=ws.settings,
        role=ctx.member.role,  # type: ignore[arg-type]
        created_at=ws.created_at,
    )


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
def update_workspace(
    body: WorkspaceUpdate,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> WorkspaceRead:
    ws = workspace_service.update_workspace(
        db,
        workspace=ctx.workspace,
        actor_id=ctx.user.id,
        name=body.name,
        settings=body.settings,
    )
    return WorkspaceRead(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        owner_id=ws.owner_id,
        plan=ws.plan,
        is_demo=ws.is_demo,
        settings=ws.settings,
        role=ctx.member.role,  # type: ignore[arg-type]
        created_at=ws.created_at,
    )


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberRead])
def list_members(
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> list[WorkspaceMemberRead]:
    rows = workspace_service.list_members(db, workspace_id=ctx.workspace.id)
    return [
        WorkspaceMemberRead(
            id=member.id,
            workspace_id=member.workspace_id,
            user_id=member.user_id,
            email=user.email,
            name=user.name,
            role=member.role,  # type: ignore[arg-type]
            joined_at=member.joined_at,
        )
        for member, user in rows
    ]


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberRead, status_code=status.HTTP_201_CREATED)
def add_member(
    body: WorkspaceMemberAdd,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> WorkspaceMemberRead:
    member, user = workspace_service.add_member_by_email(
        db,
        workspace=ctx.workspace,
        actor_id=ctx.user.id,
        email=body.email,
        role=body.role,
    )
    return WorkspaceMemberRead(
        id=member.id,
        workspace_id=member.workspace_id,
        user_id=member.user_id,
        email=user.email,
        name=user.name,
        role=member.role,  # type: ignore[arg-type]
        joined_at=member.joined_at,
    )


@router.patch("/{workspace_id}/members/{member_id}", response_model=WorkspaceMemberRead)
def update_member_role(
    member_id: uuid.UUID,
    body: WorkspaceMemberUpdate,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> WorkspaceMemberRead:
    member, user = workspace_service.update_member_role(
        db,
        workspace=ctx.workspace,
        actor_member=ctx.member,
        member_id=member_id,
        new_role=body.role,
    )
    return WorkspaceMemberRead(
        id=member.id,
        workspace_id=member.workspace_id,
        user_id=member.user_id,
        email=user.email,
        name=user.name,
        role=member.role,  # type: ignore[arg-type]
        joined_at=member.joined_at,
    )


@router.delete("/{workspace_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    member_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> Response:
    workspace_service.remove_member(
        db,
        workspace=ctx.workspace,
        actor_id=ctx.user.id,
        member_id=member_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workspace_id}/api-keys", response_model=list[APIKeyRead])
def list_api_keys(
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> list[APIKeyRead]:
    keys = api_key_service.list_api_keys(db, workspace_id=ctx.workspace.id)
    return [APIKeyRead.model_validate(k) for k in keys]


@router.post("/{workspace_id}/api-keys", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: APIKeyCreate,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> APIKeyCreateResponse:
    key, plaintext = api_key_service.create_api_key(
        db,
        workspace_id=ctx.workspace.id,
        actor_id=ctx.user.id,
        name=body.name,
        scopes=body.scopes,
    )
    return APIKeyCreateResponse(
        api_key=APIKeyRead.model_validate(key),
        plaintext_key=plaintext,
    )


@router.delete("/{workspace_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> Response:
    api_key_service.revoke_api_key(
        db,
        workspace_id=ctx.workspace.id,
        key_id=key_id,
        actor_id=ctx.user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workspace_id}/usage", response_model=UsageSummaryRead)
def get_usage(
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> UsageSummaryRead:
    return usage_service.get_workspace_usage_summary(db, workspace=ctx.workspace)


@router.get("/{workspace_id}/audit-logs", response_model=PaginatedResponse[AuditLogRead])
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> PaginatedResponse[AuditLogRead]:
    total = db.scalar(select(func.count(AuditLog.id)).where(AuditLog.workspace_id == ctx.workspace.id)) or 0
    rows = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.workspace_id == ctx.workspace.id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    return PaginatedResponse(
        items=[AuditLogRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
