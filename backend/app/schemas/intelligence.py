from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MonitorType = Literal[
    "expected_interval",
    "expected_count",
    "required_output_fields",
    "http_endpoint",
    "webhook_confirmation",
    "external_record_check",
]


class InvestigationOutputSchema(BaseModel):
    """Structured JSON schema required from AI and deterministic analyzers."""

    summary: str = Field(min_length=5, max_length=1000)
    root_cause_hypothesis: str = Field(min_length=5, max_length=1500)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list, max_length=15)
    possible_causes: list[str] = Field(default_factory=list, max_length=10)
    recommended_actions: list[str] = Field(default_factory=list, max_length=10)
    severity_assessment: Literal["critical", "high", "medium", "low", "informational"]
    requires_human_review: bool = True


class InvestigationStartRequest(BaseModel):
    run_async: bool = False


class AIInvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    workspace_id: uuid.UUID
    provider: str
    model: str
    analysis_status: str
    summary: str | None = None
    root_cause_hypothesis: str | None = None
    confidence: float | None = None
    evidence: list[str]
    possible_causes: list[str]
    recommended_actions: list[str]
    severity_assessment: str | None = None
    requires_human_review: bool
    token_usage: dict[str, Any]
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class OutcomeMonitorCreate(BaseModel):
    workflow_id: uuid.UUID
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    monitor_type: MonitorType
    configuration: dict[str, Any] = Field(default_factory=dict)
    expected_result: dict[str, Any] = Field(default_factory=dict)
    schedule_seconds: int = Field(default=300, ge=60, le=86400)
    severity: Literal["critical", "high", "medium", "low"] = "high"
    enabled: bool = True


class OutcomeMonitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    configuration: dict[str, Any] | None = None
    expected_result: dict[str, Any] | None = None
    schedule_seconds: int | None = Field(default=None, ge=60, le=86400)
    severity: Literal["critical", "high", "medium", "low"] | None = None
    enabled: bool | None = None


class OutcomeMonitorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str | None = None
    name: str
    description: str | None = None
    monitor_type: str
    configuration: dict[str, Any]
    expected_result: dict[str, Any]
    schedule_seconds: int
    severity: str
    enabled: bool
    status: str
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    failure_evidence: dict[str, Any] | None = None
    is_demo: bool
    created_at: datetime


class OutcomeMonitorRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    monitor_id: uuid.UUID
    workspace_id: uuid.UUID
    passed: bool
    evidence: dict[str, Any]
    duration_ms: int | None = None
    checked_at: datetime


class OutcomeCheckResult(BaseModel):
    monitor: OutcomeMonitorRead
    run: OutcomeMonitorRunRead
    incident_id: uuid.UUID | None = None
