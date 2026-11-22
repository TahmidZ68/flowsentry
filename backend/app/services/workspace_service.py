from __future__ import annotations

import re
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.plans import get_plan_limits
from app.models.identity import Project, User, Workspace, WorkspaceMember
from app.services.audit_service import record_audit_log


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return f"{base[:64]}-{secrets.token_hex(3)}"


def get_or_create_user(
    db: Session,
    *,
    user_id: uuid.UUID,
    email: str,
    name: str | None = None,
    avatar_url: str | None = None,
) -> User:
    user = db.get(User, user_id)
    if user is None:
        existing_by_email = db.scalar(select(User).where(User.email == email.lower()))
        if existing_by_email is not None:
            return existing_by_email
        user = User(
            id=user_id,
            email=email.lower(),
            name=name,
            avatar_url=avatar_url,
        )
        db.add(user)
        db.flush()
    else:
        changed = False
        if name and user.name != name:
            user.name = name
            changed = True
        if avatar_url and user.avatar_url != avatar_url:
            user.avatar_url = avatar_url
            changed = True
        if changed:
            db.flush()
    return user


def create_workspace(
    db: Session,
    *,
    owner: User,
    name: str,
    slug: str | None = None,
) -> tuple[Workspace, WorkspaceMember]:
    resolved_slug = slug.lower().strip() if slug else _slugify(name)
    if db.scalar(select(Workspace).where(Workspace.slug == resolved_slug)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "WORKSPACE_SLUG_TAKEN", "message": "Workspace slug is already in use"},
        )

    ws = Workspace(
        name=name.strip(),
        slug=resolved_slug,
        owner_id=owner.id,
        plan="free",
        is_demo=False,
        settings={"grouping_window_hours": 24, "recovery_consecutive_successes": 3},
    )
    db.add(ws)
    db.flush()

    member = WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role="owner")
    db.add(member)

    default_project = Project(
        workspace_id=ws.id,
        name="Default Project",
        description="Primary production automation environment",
        environment="production",
    )
    db.add(default_project)

    record_audit_log(
        db,
        workspace_id=ws.id,
        user_id=owner.id,
        action="workspace.created",
        resource_type="workspace",
        resource_id=ws.id,
        metadata={"name": ws.name, "slug": ws.slug},
    )
    db.commit()
    db.refresh(ws)
    db.refresh(member)
    return ws, member


def list_user_workspaces(db: Session, *, user_id: uuid.UUID) -> list[tuple[Workspace, str]]:
    rows = db.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.created_at.asc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def update_workspace(
    db: Session,
    *,
    workspace: Workspace,
    actor_id: uuid.UUID,
    name: str | None,
    settings: dict | None,
) -> Workspace:
    if name is not None:
        workspace.name = name.strip()
    if settings is not None:
        merged = dict(workspace.settings or {})
        merged.update(settings)
        workspace.settings = merged

    record_audit_log(
        db,
        workspace_id=workspace.id,
        user_id=actor_id,
        action="workspace.updated",
        resource_type="workspace",
        resource_id=workspace.id,
        metadata={"name": workspace.name},
    )
    db.commit()
    db.refresh(workspace)
    return workspace


def list_members(db: Session, *, workspace_id: uuid.UUID) -> list[tuple[WorkspaceMember, User]]:
    rows = db.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(WorkspaceMember.joined_at.asc())
    ).all()
    return [(row[0], row[1]) for row in rows]


def add_member_by_email(
    db: Session,
    *,
    workspace: Workspace,
    actor_id: uuid.UUID,
    email: str,
    role: str,
) -> tuple[WorkspaceMember, User]:
    limits = get_plan_limits(workspace.plan)
    current_count = (
        db.scalar(select(func.count(WorkspaceMember.id)).where(WorkspaceMember.workspace_id == workspace.id)) or 0
    )
    if current_count >= limits.max_members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PLAN_LIMIT_REACHED",
                "message": f"Current plan ({limits.display_name}) allows at most {limits.max_members} member(s)",
            },
        )

    target_user = db.scalar(select(User).where(User.email == email.lower().strip()))
    if target_user is None:
        # Pre-provision invited user record deterministically; Supabase sub reconciliation matches by email if needed
        target_user = User(email=email.lower().strip(), name=email.split("@")[0])
        db.add(target_user)
        db.flush()

    existing = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == target_user.id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ALREADY_MEMBER", "message": "User is already a member of this workspace"},
        )

    member = WorkspaceMember(workspace_id=workspace.id, user_id=target_user.id, role=role)
    db.add(member)
    record_audit_log(
        db,
        workspace_id=workspace.id,
        user_id=actor_id,
        action="member.added",
        resource_type="workspace_member",
        resource_id=target_user.id,
        metadata={"email": target_user.email, "role": role},
    )
    db.commit()
    db.refresh(member)
    return member, target_user


def update_member_role(
    db: Session,
    *,
    workspace: Workspace,
    actor_member: WorkspaceMember,
    member_id: uuid.UUID,
    new_role: str,
) -> tuple[WorkspaceMember, User]:
    target = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == workspace.id,
        )
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEMBER_NOT_FOUND", "message": "Workspace member not found"},
        )
    if target.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CANNOT_MODIFY_OWNER", "message": "Workspace owner role cannot be modified"},
        )
    if new_role == "admin" and actor_member.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Only workspace owners can promote members to admin"},
        )

    old_role = target.role
    target.role = new_role
    user = db.get(User, target.user_id)
    record_audit_log(
        db,
        workspace_id=workspace.id,
        user_id=actor_member.user_id,
        action="member.role_updated",
        resource_type="workspace_member",
        resource_id=target.id,
        metadata={"old_role": old_role, "new_role": new_role},
    )
    db.commit()
    db.refresh(target)
    return target, user  # type: ignore[return-value]


def remove_member(
    db: Session,
    *,
    workspace: Workspace,
    actor_id: uuid.UUID,
    member_id: uuid.UUID,
) -> None:
    target = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.id == member_id,
            WorkspaceMember.workspace_id == workspace.id,
        )
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEMBER_NOT_FOUND", "message": "Workspace member not found"},
        )
    if target.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CANNOT_REMOVE_OWNER", "message": "Workspace owner cannot be removed"},
        )

    record_audit_log(
        db,
        workspace_id=workspace.id,
        user_id=actor_id,
        action="member.removed",
        resource_type="workspace_member",
        resource_id=target.id,
        metadata={"removed_user_id": str(target.user_id)},
    )
    db.delete(target)
    db.commit()
