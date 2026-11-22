from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, require_workspace_role
from app.db.session import get_db
from app.integrations.n8n import parse_n8n_error_webhook
from app.models.monitoring import Integration
from app.schemas.monitoring import (
    IngestResultRead,
    IntegrationCreate,
    IntegrationCreateResponse,
    IntegrationRead,
    IntegrationSyncResult,
    IntegrationUpdate,
    IntegrationValidationResult,
)
from app.services import ingestion_service, integration_service

router = APIRouter(prefix="/workspaces/{workspace_id}/integrations", tags=["Integrations"])


def _to_read(integration: Integration) -> IntegrationRead:
    return IntegrationRead(
        id=integration.id,
        workspace_id=integration.workspace_id,
        project_id=integration.project_id,
        provider=integration.provider,
        connection_name=integration.connection_name,
        base_url=integration.base_url,
        polling_enabled=integration.polling_enabled,
        polling_interval_seconds=integration.polling_interval_seconds,
        status=integration.status,
        last_error=integration.last_error,
        last_connected_at=integration.last_connected_at,
        last_synced_at=integration.last_synced_at,
        has_credentials=bool(
            integration.status != "disconnected"
            and integration.encrypted_credentials
            and integration.encrypted_credentials != "{}"
        ),
        created_at=integration.created_at,
    )


@router.get("", response_model=list[IntegrationRead])
def list_integrations(
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> list[IntegrationRead]:
    items = integration_service.list_integrations(db, workspace_id=ctx.workspace.id)
    return [_to_read(item) for item in items]


@router.post("", response_model=IntegrationCreateResponse, status_code=status.HTTP_201_CREATED)
def create_integration(
    body: IntegrationCreate,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> IntegrationCreateResponse:
    integration, webhook_secret = integration_service.create_integration(
        db,
        workspace=ctx.workspace,
        actor_id=ctx.user.id,
        payload=body,
    )
    return IntegrationCreateResponse(
        integration=_to_read(integration),
        webhook_secret=webhook_secret,
        webhook_url_path=f"/api/v1/ingest/webhooks/n8n/{integration.id}",
    )


@router.patch("/{integration_id}", response_model=IntegrationRead)
def update_integration(
    integration_id: uuid.UUID,
    body: IntegrationUpdate,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> IntegrationRead:
    updated = integration_service.update_integration(
        db,
        workspace_id=ctx.workspace.id,
        integration_id=integration_id,
        actor_id=ctx.user.id,
        payload=body,
    )
    return _to_read(updated)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_integration(
    integration_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> Response:
    integration_service.disconnect_integration(
        db,
        workspace_id=ctx.workspace.id,
        integration_id=integration_id,
        actor_id=ctx.user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{integration_id}/validate", response_model=IntegrationValidationResult)
def validate_integration(
    integration_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
) -> IntegrationValidationResult:
    return integration_service.validate_n8n_integration(
        db,
        workspace_id=ctx.workspace.id,
        integration_id=integration_id,
        actor_id=ctx.user.id,
    )


@router.post("/{integration_id}/sync", response_model=IntegrationSyncResult)
def sync_integration(
    integration_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> IntegrationSyncResult:
    return integration_service.sync_n8n_integration(
        db,
        workspace=ctx.workspace,
        integration_id=integration_id,
        actor_id=ctx.user.id,
    )


@router.post("/{integration_id}/test-webhook", response_model=IngestResultRead)
def send_safe_test_webhook(
    integration_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_workspace_role("member")),
    db: Session = Depends(get_db),
) -> IngestResultRead:
    """
    Safe local test helper simulating an n8n Error Trigger webhook payload
    so users can test the ingestion & detection pipeline without exposing n8n publicly.
    """
    integration = integration_service._get_workspace_integration(
        db, workspace_id=ctx.workspace.id, integration_id=integration_id
    )
    now_iso = datetime.now(UTC).isoformat()
    sample_payload = {
        "execution": {
            "id": f"local-test-{uuid.uuid4().hex[:8]}",
            "mode": "webhook",
            "startedAt": now_iso,
            "stoppedAt": now_iso,
            "lastNodeExecuted": "Create CRM Contact",
            "error": {
                "message": "HTTP 429 Too Many Requests: Rate limit exceeded by CRM API",
            },
        },
        "workflow": {
            "id": "local-test-wf-1",
            "name": "Local Test Lead Sync Workflow",
        },
    }
    event = parse_n8n_error_webhook(
        sample_payload,
        workspace_id=ctx.workspace.id,
        project_id=integration.project_id,
    )
    execution, workflow, deduplicated, detection = ingestion_service.ingest_normalized_event(
        db,
        workspace=ctx.workspace,
        integration=integration,
        event=event,
    )
    db.commit()
    return IngestResultRead(
        execution_id=execution.id,
        workflow_id=workflow.id,
        deduplicated=deduplicated,
        incident_id=detection.incident.id if detection.incident else None,
        incident_action=detection.action,
    )
