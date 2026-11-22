from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ExecutionStatus = Literal["success", "failed", "running", "waiting", "canceled", "unknown"]
IncidentSeverity = Literal["critical", "high", "medium", "low", "informational"]
IncidentStatus = Literal["open", "acknowledged", "investigating", "resolved", "reopened"]


class NormalizedExecutionEvent(BaseModel):
    """Canonical internal execution schema (v1.0) across all automation providers."""

    schema_version: str = "1.0"
    provider: str = Field(min_length=1, max_length=32)
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    workflow_id: uuid.UUID | None = None
    external_workflow_id: str = Field(min_length=1, max_length=255)
    workflow_name: str | None = Field(default=None, max_length=255)
    external_execution_id: str = Field(min_length=1, max_length=255)
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    failed_node: str | None = Field(default=None, max_length=255)
    error_type: str | None = Field(default=None, max_length=128)
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DirectExecutionIngestRequest(BaseModel):
    project_id: uuid.UUID
    provider: str = Field(default="custom_webhook", min_length=1, max_length=32)
    external_workflow_id: str = Field(min_length=1, max_length=255)
    workflow_name: str = Field(min_length=1, max_length=255)
    external_execution_id: str = Field(min_length=1, max_length=255)
    status: ExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    failed_node: str | None = Field(default=None, max_length=255)
    error_type: str | None = Field(default=None, max_length=128)
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationCreate(BaseModel):
    project_id: uuid.UUID
    provider: Literal["n8n", "custom_webhook"] = "n8n"
    connection_name: str = Field(min_length=2, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=512)
    polling_enabled: bool = True
    polling_interval_seconds: int = Field(default=120, ge=30, le=3600)


class IntegrationUpdate(BaseModel):
    connection_name: str | None = Field(default=None, min_length=2, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, max_length=512)
    polling_enabled: bool | None = None
    polling_interval_seconds: int | None = Field(default=None, ge=30, le=3600)


class IntegrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    provider: str
    connection_name: str
    base_url: str | None = None
    polling_enabled: bool
    polling_interval_seconds: int
    status: str
    last_error: str | None = None
    last_connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    has_credentials: bool = True
    created_at: datetime


class IntegrationCreateResponse(BaseModel):
    integration: IntegrationRead
    webhook_secret: str
    webhook_url_path: str


class IntegrationValidationResult(BaseModel):
    ok: bool
    status: str
    message: str
    workflows_accessible: int = 0


class IntegrationSyncResult(BaseModel):
    workflows_synced: int
    executions_ingested: int
    executions_deduplicated: int
    incidents_created: int
    incidents_updated: int


class WorkflowRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID
    integration_id: uuid.UUID
    external_workflow_id: str
    name: str
    description: str | None = None
    enabled: bool
    max_duration_ms: int | None = None
    expected_interval_seconds: int | None = None
    is_demo: bool
    execution_count: int = 0
    failed_count: int = 0
    failure_rate: float = 0.0
    avg_duration_ms: float | None = None
    last_execution_at: datetime | None = None
    last_execution_status: str | None = None
    active_incidents_count: int = 0
    created_at: datetime


class WorkflowUpdate(BaseModel):
    max_duration_ms: int | None = Field(default=None, ge=100, le=86_400_000)
    expected_interval_seconds: int | None = Field(default=None, ge=60, le=2_592_000)
    enabled: bool | None = None


class ExecutionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    event_type: str
    node_name: str | None = None
    event_timestamp: datetime
    event_payload: dict[str, Any]


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    workflow_id: uuid.UUID
    external_execution_id: str
    schema_version: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    failed_node: str | None = None
    error_type: str | None = None
    error_summary: str | None = None
    normalized_payload: dict[str, Any]
    is_demo: bool
    created_at: datetime


class ExecutionDetailRead(ExecutionRead):
    events: list[ExecutionEventRead] = Field(default_factory=list)
    workflow_name: str | None = None


class IngestResultRead(BaseModel):
    execution_id: uuid.UUID
    workflow_id: uuid.UUID
    deduplicated: bool
    incident_id: uuid.UUID | None = None
    incident_action: str | None = None


class IncidentNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    author_id: uuid.UUID | None = None
    note_type: str
    content: str
    created_at: datetime


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str | None = None
    title: str
    description: str | None = None
    severity: str
    status: str
    fingerprint: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
    assigned_to_user_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    resolution_reason: str | None = None
    resolution_notes: str | None = None
    is_demo: bool
    created_at: datetime


class IncidentDetailRead(IncidentRead):
    notes: list[IncidentNoteRead] = Field(default_factory=list)
    recent_executions: list[ExecutionRead] = Field(default_factory=list)


class IncidentAssignRequest(BaseModel):
    user_id: uuid.UUID | None = None


class IncidentResolveRequest(BaseModel):
    resolution_notes: str | None = Field(default=None, max_length=2000)


class IncidentNoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class TrendPoint(BaseModel):
    date: str
    total: int
    success: int
    failed: int


class OverviewMetricsRead(BaseModel):
    total_workflows: int
    healthy_workflows: int
    total_executions: int
    successful_executions: int
    failed_executions: int
    active_incidents: int
    critical_incidents: int
    monitors_total: int
    monitors_failing: int
    trends: list[TrendPoint]
    recent_incidents: list[IncidentRead]
    recent_executions: list[ExecutionRead]
