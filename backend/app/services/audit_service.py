from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.identity import AuditLog


def record_audit_log(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        workspace_id=workspace_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        metadata_json=metadata or {},
    )
    db.add(entry)
    return entry
