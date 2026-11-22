from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import JSONType
from app.models.identity import utcnow


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("idx_incidents_ws_status_last", "workspace_id", "status", "last_seen_at"),
        Index("idx_incidents_ws_fingerprint", "workspace_id", "fingerprint"),
        Index("idx_incidents_workflow", "workflow_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(32), default="high", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    grouping_window_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class IncidentOccurrence(Base):
    __tablename__ = "incident_occurrences"
    __table_args__ = (UniqueConstraint("incident_id", "execution_id", name="uq_incident_execution"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IncidentNote(Base):
    __tablename__ = "incident_notes"
    __table_args__ = (Index("idx_incident_notes_incident", "incident_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note_type: Mapped[str] = mapped_column(String(32), default="comment", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AIInvestigation(Base):
    __tablename__ = "ai_investigations"
    __table_args__ = (Index("idx_ai_investigations_incident", "incident_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    analysis_status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    evidence: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    possible_causes: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    recommended_actions: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    severity_assessment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    token_usage: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
