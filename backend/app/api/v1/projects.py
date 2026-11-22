from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, require_workspace_role
from app.db.session import get_db
from app.schemas.identity import PaginatedResponse, ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/workspaces/{workspace_id}/projects", tags=["Projects"])


@router.get("", response_model=PaginatedResponse[ProjectRead])
def list_projects(
    environment: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ProjectRead]:
    items, total = project_service.list_projects(
        db,
        workspace_id=ctx.workspace.id,
        environment=environment,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=[ProjectRead.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> ProjectRead:
    project = project_service.create_project(
        db,
        workspace=ctx.workspace,
        actor_id=ctx.user.id,
        name=body.name,
        description=body.description,
        environment=body.environment,
    )
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> ProjectRead:
    project = project_service.update_project(
        db,
        workspace_id=ctx.workspace.id,
        project_id=project_id,
        actor_id=ctx.user.id,
        name=body.name,
        description=body.description,
        environment=body.environment,
    )
    return ProjectRead.model_validate(project)
