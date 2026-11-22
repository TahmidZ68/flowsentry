from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.identity import User
from app.schemas.identity import WorkspaceRead
from app.services.demo_service import seed_or_reset_demo_workspace

router = APIRouter(prefix="/demo", tags=["Demo"])


@router.post("/seed", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def seed_or_reset_demo(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceRead:
    ws = seed_or_reset_demo_workspace(db, owner=current_user)
    return WorkspaceRead(
        id=ws.id,
        name=ws.name,
        slug=ws.slug,
        owner_id=ws.owner_id,
        plan=ws.plan,
        is_demo=ws.is_demo,
        settings=ws.settings,
        role="owner",
        created_at=ws.created_at,
    )
