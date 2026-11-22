from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.encryption import decrypt_json, encrypt_json
from app.core.plans import get_plan_limits
from app.core.security import hash_secret_token
from app.core.ssrf import SSRFValidationError, validate_outbound_url
from app.integrations.n8n import N8nClient, N8nClientError, parse_n8n_api_execution
from app.models.identity import Project, Workspace
from app.models.monitoring import Integration, Workflow
from app.schemas.monitoring import (
    IntegrationCreate,
    IntegrationSyncResult,
    IntegrationUpdate,
    IntegrationValidationResult,
)
from app.services.audit_service import record_audit_log
from app.services.ingestion_service import ingest_normalized_event


def _get_workspace_integration(db: Session, *, workspace_id: uuid.UUID, integration_id: uuid.UUID) -> Integration:
    integration = db.scalar(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.workspace_id == workspace_id,
        )
    )
    if integration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "INTEGRATION_NOT_FOUND", "message": "Integration not found"},
        )
    return integration


def list_integrations(db: Session, *, workspace_id: uuid.UUID) -> list[Integration]:
    return list(
        db.scalars(
            select(Integration).where(Integration.workspace_id == workspace_id).order_by(Integration.created_at.desc())
        ).all()
    )


def create_integration(
    db: Session,
    *,
    workspace: Workspace,
    actor_id: uuid.UUID,
    payload: IntegrationCreate,
) -> tuple[Integration, str]:
    limits = get_plan_limits(workspace.plan)
    active_count = (
        db.scalar(
            select(func.count(Integration.id)).where(
                Integration.workspace_id == workspace.id,
                Integration.status != "disconnected",
            )
        )
        or 0
    )
    if active_count >= limits.max_integrations:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PLAN_LIMIT_REACHED",
                "message": (
                    f"Current plan ({limits.display_name}) allows at most "
                    f"{limits.max_integrations} integration(s)"
                ),
            },
        )

    project = db.scalar(
        select(Project).where(
            Project.id == payload.project_id,
            Project.workspace_id == workspace.id,
        )
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "PROJECT_NOT_FOUND", "message": "Project not found in workspace"},
        )

    validated_url: str | None = None
    if payload.provider == "n8n":
        if not payload.base_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "BASE_URL_REQUIRED", "message": "n8n instance URL is required"},
            )
        try:
            validated_url = validate_outbound_url(payload.base_url).rstrip("/")
        except SSRFValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_URL", "message": str(exc)},
            ) from exc

    cred_dict = {"api_key": payload.api_key} if payload.api_key else {}
    encrypted = encrypt_json(cred_dict)

    raw_webhook_secret = f"fs_whsec_{secrets.token_urlsafe(32)}"
    webhook_secret_hash = hash_secret_token(raw_webhook_secret)

    integration = Integration(
        workspace_id=workspace.id,
        project_id=project.id,
        provider=payload.provider,
        connection_name=payload.connection_name.strip(),
        base_url=validated_url,
        encrypted_credentials=encrypted,
        webhook_secret_hash=webhook_secret_hash,
        polling_enabled=payload.polling_enabled if payload.provider == "n8n" else False,
        polling_interval_seconds=payload.polling_interval_seconds,
        status="pending" if payload.provider == "n8n" else "connected",
    )
    db.add(integration)
    db.flush()

    record_audit_log(
        db,
        workspace_id=workspace.id,
        user_id=actor_id,
        action="integration.created",
        resource_type="integration",
        resource_id=integration.id,
        metadata={"provider": integration.provider, "connection_name": integration.connection_name},
    )
    db.commit()
    db.refresh(integration)
    return integration, raw_webhook_secret


def update_integration(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    integration_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: IntegrationUpdate,
) -> Integration:
    integration = _get_workspace_integration(db, workspace_id=workspace_id, integration_id=integration_id)
    if payload.connection_name is not None:
        integration.connection_name = payload.connection_name.strip()
    if payload.base_url is not None:
        try:
            integration.base_url = validate_outbound_url(payload.base_url).rstrip("/")
        except SSRFValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "INVALID_URL", "message": str(exc)},
            ) from exc
    if payload.api_key is not None:
        integration.encrypted_credentials = encrypt_json({"api_key": payload.api_key})
    if payload.polling_enabled is not None:
        integration.polling_enabled = payload.polling_enabled
    if payload.polling_interval_seconds is not None:
        integration.polling_interval_seconds = payload.polling_interval_seconds

    record_audit_log(
        db,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="integration.updated",
        resource_type="integration",
        resource_id=integration.id,
        metadata={"connection_name": integration.connection_name},
    )
    db.commit()
    db.refresh(integration)
    return integration


def disconnect_integration(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    integration_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    integration = _get_workspace_integration(db, workspace_id=workspace_id, integration_id=integration_id)
    # Scrub credentials immediately on disconnect
    integration.encrypted_credentials = ""
    integration.webhook_secret_hash = None
    integration.polling_enabled = False
    integration.status = "disconnected"
    integration.last_error = None

    record_audit_log(
        db,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="integration.disconnected",
        resource_type="integration",
        resource_id=integration.id,
        metadata={"provider": integration.provider},
    )
    db.commit()


def validate_n8n_integration(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    integration_id: uuid.UUID,
    actor_id: uuid.UUID,
    transport: httpx.BaseTransport | None = None,
) -> IntegrationValidationResult:
    integration = _get_workspace_integration(db, workspace_id=workspace_id, integration_id=integration_id)
    if integration.provider != "n8n":
        return IntegrationValidationResult(
            ok=True,
            status=integration.status,
            message="Webhook integration is ready to receive events",
        )
    if not integration.base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_BASE_URL", "message": "Integration base_url is missing"},
        )

    creds = decrypt_json(integration.encrypted_credentials)
    api_key = creds.get("api_key", "")
    if not api_key:
        integration.status = "error"
        integration.last_error = "No n8n API key configured"
        db.commit()
        return IntegrationValidationResult(ok=False, status="error", message="No n8n API key configured")

    try:
        client = N8nClient(integration.base_url, api_key, transport=transport)
        count = client.validate_connection()
        integration.status = "connected"
        integration.last_connected_at = datetime.now(UTC)
        integration.last_error = None
        record_audit_log(
            db,
            workspace_id=workspace_id,
            user_id=actor_id,
            action="integration.validated",
            resource_type="integration",
            resource_id=integration.id,
            metadata={"status": "connected"},
        )
        db.commit()
        return IntegrationValidationResult(
            ok=True,
            status="connected",
            message="Connected to n8n REST API v1 successfully",
            workflows_accessible=count,
        )
    except (SSRFValidationError, N8nClientError) as exc:
        integration.status = "error"
        integration.last_error = str(exc)
        db.commit()
        return IntegrationValidationResult(ok=False, status="error", message=str(exc))


def sync_n8n_integration(
    db: Session,
    *,
    workspace: Workspace,
    integration_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
    transport: httpx.BaseTransport | None = None,
) -> IntegrationSyncResult:
    integration = _get_workspace_integration(db, workspace_id=workspace.id, integration_id=integration_id)
    if integration.provider != "n8n" or not integration.base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SYNC_NOT_SUPPORTED", "message": "Only configured n8n integrations can be synced"},
        )
    if integration.status == "disconnected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INTEGRATION_DISCONNECTED", "message": "Disconnected integration cannot be synced"},
        )

    creds = decrypt_json(integration.encrypted_credentials)
    api_key = creds.get("api_key", "")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_API_KEY", "message": "n8n API key is not configured"},
        )

    try:
        client = N8nClient(integration.base_url, api_key, transport=transport)
        remote_workflows = client.list_workflows()
    except (SSRFValidationError, N8nClientError) as exc:
        integration.status = "error"
        integration.last_error = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "N8N_SYNC_FAILED", "message": str(exc)},
        ) from exc

    wf_names: dict[str, str] = {}
    for item in remote_workflows:
        ext_id = str(item.get("id") or "")
        if not ext_id:
            continue
        name = str(item.get("name") or f"Workflow {ext_id}")[:255]
        wf_names[ext_id] = name
        wf = db.scalar(
            select(Workflow).where(
                Workflow.integration_id == integration.id,
                Workflow.external_workflow_id == ext_id,
            )
        )
        if wf is None:
            wf = Workflow(
                workspace_id=workspace.id,
                project_id=integration.project_id,
                integration_id=integration.id,
                external_workflow_id=ext_id,
                name=name,
                enabled=bool(item.get("active", True)),
                is_demo=workspace.is_demo,
                metadata_json={"triggerCount": item.get("triggerCount")},
            )
            db.add(wf)
        else:
            wf.name = name
            wf.enabled = bool(item.get("active", True))
    db.flush()

    started_after = (
        integration.last_synced_at - timedelta(minutes=2)
        if integration.last_synced_at
        else datetime.now(UTC) - timedelta(days=7)
    )
    try:
        remote_executions, next_cursor = client.list_executions(started_after=started_after)
    except (SSRFValidationError, N8nClientError) as exc:
        integration.status = "error"
        integration.last_error = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "N8N_SYNC_FAILED", "message": str(exc)},
        ) from exc

    ingested = 0
    deduplicated = 0
    incidents_created = 0
    incidents_updated = 0

    for raw_exec in remote_executions:
        ext_wf_id = str(raw_exec.get("workflowId") or "")
        event = parse_n8n_api_execution(
            raw_exec,
            workspace_id=workspace.id,
            project_id=integration.project_id,
            workflow_name=wf_names.get(ext_wf_id),
        )
        if not event.external_execution_id:
            continue
        _, _, was_dup, outcome = ingest_normalized_event(
            db,
            workspace=workspace,
            integration=integration,
            event=event,
        )
        if was_dup:
            deduplicated += 1
        else:
            ingested += 1
            if outcome.action == "created":
                incidents_created += 1
            elif outcome.action == "grouped":
                incidents_updated += 1

    now = datetime.now(UTC)
    integration.status = "connected"
    integration.last_connected_at = now
    integration.last_synced_at = now
    integration.sync_cursor = next_cursor
    integration.last_error = None

    if actor_id:
        record_audit_log(
            db,
            workspace_id=workspace.id,
            user_id=actor_id,
            action="integration.synced",
            resource_type="integration",
            resource_id=integration.id,
            metadata={
                "workflows_synced": len(wf_names),
                "executions_ingested": ingested,
                "executions_deduplicated": deduplicated,
            },
        )
    db.commit()

    return IntegrationSyncResult(
        workflows_synced=len(wf_names),
        executions_ingested=ingested,
        executions_deduplicated=deduplicated,
        incidents_created=incidents_created,
        incidents_updated=incidents_updated,
    )
