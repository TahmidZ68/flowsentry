from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.identity import Workspace
from app.models.monitoring import Integration
from app.services.integration_service import sync_n8n_integration
from app.workers.celery_app import celery_app

logger = logging.getLogger("flowsentry.workers")


@celery_app.task(name="flowsentry.sync_integration")
def sync_integration_task(integration_id: str) -> dict[str, int | str]:
    with SessionLocal() as db:
        integration = db.get(Integration, uuid.UUID(integration_id))
        if integration is None or integration.status == "disconnected":
            return {"status": "skipped"}
        workspace = db.get(Workspace, integration.workspace_id)
        if workspace is None:
            return {"status": "skipped"}
        result = sync_n8n_integration(db, workspace=workspace, integration_id=integration.id)
        return {
            "status": "ok",
            "workflows_synced": result.workflows_synced,
            "executions_ingested": result.executions_ingested,
        }


@celery_app.task(name="flowsentry.poll_enabled_integrations")
def poll_enabled_integrations() -> dict[str, int]:
    polled = 0
    errors = 0
    with SessionLocal() as db:
        integrations = list(
            db.scalars(
                select(Integration).where(
                    Integration.provider == "n8n",
                    Integration.polling_enabled.is_(True),
                    Integration.status.in_(("connected", "pending")),
                )
            ).all()
        )
        for integration in integrations:
            workspace = db.get(Workspace, integration.workspace_id)
            if workspace is None:
                continue
            try:
                sync_n8n_integration(db, workspace=workspace, integration_id=integration.id)
                polled += 1
            except Exception as exc:
                errors += 1
                logger.warning("Polling integration %s failed: %s", integration.id, exc)
    return {"polled": polled, "errors": errors}
