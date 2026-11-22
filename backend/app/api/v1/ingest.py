from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import enforce_rate_limit, require_ingest_auth
from app.core.security import verify_hashed_secret
from app.db.session import get_db
from app.integrations.n8n import parse_n8n_error_webhook
from app.models.identity import Project, Workspace
from app.models.monitoring import Integration
from app.schemas.monitoring import DirectExecutionIngestRequest, IngestResultRead, NormalizedExecutionEvent
from app.services import ingestion_service

router = APIRouter(tags=["Ingestion"])

MAX_WEBHOOK_PAYLOAD_BYTES = 1_048_576


async def enforce_webhook_body_limit(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_WEBHOOK_PAYLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": f"Webhook payload exceeds {MAX_WEBHOOK_PAYLOAD_BYTES} byte limit",
                    },
                )
        except ValueError:
            pass

    body = await request.body()
    if len(body) > MAX_WEBHOOK_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "PAYLOAD_TOO_LARGE",
                "message": f"Webhook payload exceeds {MAX_WEBHOOK_PAYLOAD_BYTES} byte limit",
            },
        )


@router.post("/ingest/webhooks/n8n/{integration_id}", response_model=IngestResultRead)
def ingest_n8n_webhook(
    integration_id: uuid.UUID,
    request: Request,
    payload: dict[str, Any] | list[dict[str, Any]] = Body(...),
    x_flowsentry_webhook_secret: str | None = Header(default=None),
    _: None = Depends(enforce_webhook_body_limit),
    db: Session = Depends(get_db),
) -> IngestResultRead:
    enforce_rate_limit(request, scope=f"webhook:{integration_id}", max_requests=180, window_seconds=60)

    integration = db.get(Integration, integration_id)
    if integration is None or integration.status == "disconnected" or not integration.webhook_secret_hash:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "INTEGRATION_NOT_FOUND", "message": "Active webhook integration not found"},
        )

    if not x_flowsentry_webhook_secret or not verify_hashed_secret(
        x_flowsentry_webhook_secret, integration.webhook_secret_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_WEBHOOK_SECRET", "message": "Invalid or missing webhook secret"},
        )

    workspace = db.get(Workspace, integration.workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WORKSPACE_NOT_FOUND", "message": "Workspace not found"},
        )

    try:
        event = parse_n8n_error_webhook(
            payload,
            workspace_id=workspace.id,
            project_id=integration.project_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_WEBHOOK_PAYLOAD", "message": str(exc)},
        ) from exc

    execution, workflow, deduplicated, detection = ingestion_service.ingest_normalized_event(
        db,
        workspace=workspace,
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


@router.post("/workspaces/{workspace_id}/executions/ingest", response_model=IngestResultRead)
def ingest_direct_execution(
    body: DirectExecutionIngestRequest,
    request: Request,
    workspace: Workspace = Depends(require_ingest_auth),
    db: Session = Depends(get_db),
) -> IngestResultRead:
    enforce_rate_limit(request, scope=f"ingest:{workspace.id}", max_requests=240, window_seconds=60)

    project = db.scalar(select(Project).where(Project.id == body.project_id, Project.workspace_id == workspace.id))
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found in workspace"},
        )

    integration = ingestion_service.get_or_create_custom_integration(db, workspace=workspace, project_id=project.id)
    event = NormalizedExecutionEvent(
        provider=body.provider,
        workspace_id=workspace.id,
        project_id=project.id,
        external_workflow_id=body.external_workflow_id,
        workflow_name=body.workflow_name,
        external_execution_id=body.external_execution_id,
        status=body.status,
        started_at=body.started_at,
        finished_at=body.finished_at,
        duration_ms=body.duration_ms,
        failed_node=body.failed_node,
        error_type=body.error_type,
        error_message=body.error_message,
        metadata=body.metadata,
    )
    execution, workflow, deduplicated, detection = ingestion_service.ingest_normalized_event(
        db,
        workspace=workspace,
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
