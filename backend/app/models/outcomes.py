from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType
from app.models.identity import utcnow


class OutcomeMonitor(Base):
    __tablename__ = "outcome_monitors"
    __table_args__ = (Index("idx_outcome_monitors_ws_enabled", "workspace_id", "enabled"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    monitor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    expected_result: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    schedule_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="high", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class OutcomeMonitorRun(Base):
    __tablename__ = "outcome_monitor_runs"
    __table_args__ = (Index("idx_monitor_runs_monitor_ts", "monitor_id", "checked_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("outcome_monitors.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("workspace_id", "channel", name="uq_notif_pref_ws_channel"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encrypted_config: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list[str]] = mapped_column(
        JSONType, default=lambda: ["critical_incident", "high_incident", "outcome_failure"], nullable=False
    )
    min_severity: Mapped[str] = mapped_column(String(32), default="high", nullable=False)
    suppression_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_ws_created", "workspace_id", "created_at"),
        Index("idx_notifications_dedup", "dedup_key", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
