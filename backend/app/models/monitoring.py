from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType
from app.models.identity import utcnow


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (Index("idx_integrations_workspace_project", "workspace_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    connection_name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_secret_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    polling_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    polling_interval_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    sync_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (
        UniqueConstraint("integration_id", "external_workflow_id", name="uq_workflow_integration_ext_id"),
        Index("idx_workflows_workspace", "workspace_id", "enabled"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False
    )
    external_workflow_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "external_execution_id", name="uq_execution_wf_ext_id"),
        Index("idx_executions_ws_started", "workspace_id", "started_at"),
        Index("idx_executions_wf_started", "workflow_id", "started_at"),
        Index("idx_executions_ws_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    external_execution_id: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), default="1.0", nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_node: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ExecutionEvent(Base):
    __tablename__ = "execution_events"
    __table_args__ = (Index("idx_execution_events_exec_ts", "execution_id", "event_timestamp"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    node_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
