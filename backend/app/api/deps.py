from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rate_limit import RateLimitExceeded, rate_limiter
from app.core.security import AuthenticationError, verify_jwt_token
from app.db.session import get_db
from app.models.identity import User, Workspace, WorkspaceMember
from app.services.workspace_service import get_or_create_user

bearer_scheme = HTTPBearer(auto_error=False)

ROLE_RANK: dict[str, int] = {
    "viewer": 1,
    "member": 2,
    "admin": 3,
    "owner": 4,
}


@dataclass(frozen=True)
class WorkspaceContext:
    user: User
    workspace: Workspace
    member: WorkspaceMember


def enforce_rate_limit(request: Request, scope: str = "api", max_requests: int = 120, window_seconds: int = 60) -> None:
    client_ip = request.client.host if request.client else "unknown"
    try:
        rate_limiter.check(f"rl:{scope}:{client_ip}", max_requests=max_requests, window_seconds=window_seconds)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "RATE_LIMITED", "message": "Too many requests; please retry shortly"},
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing or invalid Authorization header"},
        )

    try:
        payload = verify_jwt_token(credentials.credentials)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN", "message": str(exc)},
        ) from exc

    sub = payload.get("sub")
    email = payload.get("email")
    if not sub or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_TOKEN_CLAIMS", "message": "Token missing required sub or email claim"},
        )

    try:
        user_uuid = uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_SUBJECT", "message": "Token sub claim is not a valid UUID"},
        ) from exc

    user_meta = payload.get("user_metadata") or {}
    name = user_meta.get("name") or user_meta.get("full_name") or payload.get("name")
    avatar_url = user_meta.get("avatar_url")

    user = get_or_create_user(
        db,
        user_id=user_uuid,
        email=str(email),
        name=str(name) if name else None,
        avatar_url=str(avatar_url) if avatar_url else None,
    )
    db.commit()
    return user


def require_workspace_role(min_role: str = "viewer"):
    required_rank = ROLE_RANK[min_role]

    def _dependency(
        workspace_id: uuid.UUID,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> WorkspaceContext:
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            # Do not reveal whether another workspace exists to non-members
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "WORKSPACE_ACCESS_DENIED", "message": "Access to workspace is denied"},
            )

        member = db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == current_user.id,
            )
        )
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "WORKSPACE_ACCESS_DENIED", "message": "You are not a member of this workspace"},
            )

        actual_rank = ROLE_RANK.get(member.role, 0)
        if actual_rank < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "INSUFFICIENT_ROLE",
                    "message": f"This action requires at least '{min_role}' role",
                },
            )

        return WorkspaceContext(user=current_user, workspace=workspace, member=member)

    return _dependency
