from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rate_limit import RateLimitExceeded, rate_limiter
from app.core.security import AuthenticationError, hash_secret_token, verify_jwt_token
from app.db.session import get_db
from app.models.identity import User, Workspace, WorkspaceAPIKey, WorkspaceMember
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


def _extract_client_ip(request: Request) -> str:
    real_ip = request.headers.get("x-real-ip")
    if real_ip and real_ip.strip():
        return real_ip.strip()
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_hop = forwarded_for.split(",", 1)[0].strip()
        if first_hop:
            return first_hop
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, scope: str = "api", max_requests: int = 120, window_seconds: int = 60) -> None:
    client_ip = _extract_client_ip(request)
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
    if db.new or db.dirty:
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


def require_ingest_auth(
    workspace_id: uuid.UUID,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "WORKSPACE_ACCESS_DENIED", "message": "Access to workspace is denied"},
        )

    if x_api_key is not None:
        key_hash = hash_secret_token(x_api_key.strip())
        api_key = db.scalar(
            select(WorkspaceAPIKey).where(
                WorkspaceAPIKey.workspace_id == workspace_id,
                WorkspaceAPIKey.key_hash == key_hash,
            )
        )
        if api_key is None or api_key.revoked_at is not None or "ingest:write" not in (api_key.scopes or []):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "INVALID_API_KEY", "message": "Invalid, revoked, or unauthorized workspace API key"},
            )
        api_key.last_used_at = datetime.now(UTC)
        return workspace

    current_user = get_current_user(credentials=credentials, db=db)
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
    if ROLE_RANK.get(member.role, 0) < ROLE_RANK["member"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "INSUFFICIENT_ROLE", "message": "This action requires at least 'member' role"},
        )
    return workspace
