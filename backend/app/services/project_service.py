from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.plans import get_plan_limits
from app.models.identity import Project, Workspace
from app.services.audit_service import record_audit_log


def list_projects(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    environment: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Project], int]:
    base_stmt = select(Project).where(Project.workspace_id == workspace_id)
    count_stmt = select(func.count(Project.id)).where(Project.workspace_id == workspace_id)
    if environment:
        base_stmt = base_stmt.where(Project.environment == environment)
        count_stmt = count_stmt.where(Project.environment == environment)

    total = db.scalar(count_stmt) or 0
    items = list(db.scalars(base_stmt.order_by(Project.created_at.asc()).limit(limit).offset(offset)).all())
    return items, total


def create_project(
    db: Session,
    *,
    workspace: Workspace,
    actor_id: uuid.UUID,
    name: str,
    description: str | None,
    environment: str,
) -> Project:
    limits = get_plan_limits(workspace.plan)
    current_count = db.scalar(select(func.count(Project.id)).where(Project.workspace_id == workspace.id)) or 0
    if current_count >= limits.max_projects:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PLAN_LIMIT_REACHED",
                "message": f"Current plan ({limits.display_name}) allows at most {limits.max_projects} project(s)",
            },
        )

    dup = db.scalar(
        select(Project).where(
            Project.workspace_id == workspace.id,
            Project.name == name.strip(),
            Project.environment == environment,
        )
    )
    if dup is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "PROJECT_EXISTS",
                "message": "A project with this name and environment already exists",
            },
        )

    project = Project(
        workspace_id=workspace.id,
        name=name.strip(),
        description=description.strip() if description else None,
        environment=environment,
    )
    db.add(project)
    db.flush()

    record_audit_log(
        db,
        workspace_id=workspace.id,
        user_id=actor_id,
        action="project.created",
        resource_type="project",
        resource_id=project.id,
        metadata={"name": project.name, "environment": project.environment},
    )
    db.commit()
    db.refresh(project)
    return project


def update_project(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str | None,
    description: str | None,
    environment: str | None,
) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id))
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found"},
        )

    if name is not None:
        project.name = name.strip()
    if description is not None:
        project.description = description.strip() or None
    if environment is not None:
        project.environment = environment

    record_audit_log(
        db,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="project.updated",
        resource_type="project",
        resource_id=project.id,
        metadata={"name": project.name, "environment": project.environment},
    )
    db.commit()
    db.refresh(project)
    return project
