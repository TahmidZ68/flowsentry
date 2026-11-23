from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import enforce_rate_limit, get_current_user
from app.core.config import get_settings
from app.core.entitlements import get_entitlement_policy
from app.core.extensions import extension_registry
from app.core.security import create_local_dev_token
from app.db.session import get_db
from app.models.identity import User
from app.schemas.identity import (
    AuthMeResponse,
    DevTokenRequest,
    DevTokenResponse,
    UserRead,
    WorkspaceRead,
)
from app.services.workspace_service import get_or_create_user, list_user_workspaces

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=AuthMeResponse)
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AuthMeResponse:
    ws_rows = list_user_workspaces(db, user_id=current_user.id)
    workspaces = [
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
        for ws, role in ws_rows
    ]
    return AuthMeResponse(user=UserRead.model_validate(current_user), workspaces=workspaces)


@router.post("/dev-token", response_model=DevTokenResponse)
def issue_dev_token(
    body: DevTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> DevTokenResponse:
    """
    Development-only endpoint for local sign-in when Supabase Cloud is not configured.
    Strictly disabled when ENVIRONMENT=production or AUTH_MODE!=local_dev.
    """
    settings = get_settings()
    if settings.ENVIRONMENT == "production" or settings.AUTH_MODE != "local_dev":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Endpoint not available"},
        )

    enforce_rate_limit(request, scope="dev_auth", max_requests=30, window_seconds=60)

    email = body.email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    user_id = existing.id if existing else uuid.uuid5(uuid.NAMESPACE_DNS, email)
    user = get_or_create_user(db, user_id=user_id, email=email, name=body.name)
    db.commit()
    db.refresh(user)

    token = create_local_dev_token(user_id=user.id, email=user.email, name=user.name)
    return DevTokenResponse(access_token=token, user=UserRead.model_validate(user))


@router.get("/capabilities", tags=["System"])
def get_capabilities() -> dict[str, object]:
    """Return active edition, entitlement enforcement status, and registered core/plugin capabilities."""
    settings = get_settings()
    policy = get_entitlement_policy()
    return {
        "edition": settings.EDITION,
        "saas_quotas_enabled": policy.enforces_quotas(),
        "auth_mode": settings.AUTH_MODE,
        "connectors": sorted(extension_registry.connectors.keys()),
        "notification_channels": sorted(extension_registry.notification_channels.keys()),
    }
