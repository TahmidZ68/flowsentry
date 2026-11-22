from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import generate_api_key
from app.models.identity import WorkspaceAPIKey
from app.services.audit_service import record_audit_log


def list_api_keys(db: Session, *, workspace_id: uuid.UUID) -> list[WorkspaceAPIKey]:
    return list(
        db.scalars(
            select(WorkspaceAPIKey)
            .where(WorkspaceAPIKey.workspace_id == workspace_id)
            .order_by(WorkspaceAPIKey.created_at.desc())
        ).all()
    )


def create_api_key(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    name: str,
    scopes: list[str],
) -> tuple[WorkspaceAPIKey, str]:
    plaintext, prefix, key_hash = generate_api_key()
    api_key = WorkspaceAPIKey(
        workspace_id=workspace_id,
        created_by_user_id=actor_id,
        name=name.strip(),
        key_prefix=prefix,
        key_hash=key_hash,
        scopes=scopes or ["ingest:write"],
    )
    db.add(api_key)
    db.flush()

    record_audit_log(
        db,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="api_key.created",
        resource_type="workspace_api_key",
        resource_id=api_key.id,
        metadata={"name": api_key.name, "key_prefix": prefix},
    )
    db.commit()
    db.refresh(api_key)
    return api_key, plaintext


def revoke_api_key(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    key_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    api_key = db.scalar(
        select(WorkspaceAPIKey).where(
            WorkspaceAPIKey.id == key_id,
            WorkspaceAPIKey.workspace_id == workspace_id,
        )
    )
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "API_KEY_NOT_FOUND", "message": "API key not found"},
        )
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)
        record_audit_log(
            db,
            workspace_id=workspace_id,
            user_id=actor_id,
            action="api_key.revoked",
            resource_type="workspace_api_key",
            resource_id=api_key.id,
            metadata={"key_prefix": api_key.key_prefix},
        )
        db.commit()
