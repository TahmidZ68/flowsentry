from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

NotificationChannel = Literal["email", "slack"]
NotificationEventType = Literal[
    "critical_incident",
    "high_incident",
    "repeated_failure",
    "outcome_failure",
    "incident_resolved",
]


class NotificationPreferenceUpsert(BaseModel):
    channel: NotificationChannel
    enabled: bool = True
    slack_webhook_url: str | None = Field(default=None, max_length=500)
    email_recipients: list[EmailStr] | None = None
    events: list[NotificationEventType] = Field(
        default_factory=lambda: ["critical_incident", "high_incident", "outcome_failure"]
    )
    min_severity: Literal["critical", "high", "medium", "low", "informational"] = "high"
    suppression_minutes: int = Field(default=30, ge=0, le=1440)


class NotificationPreferenceRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    channel: str
    enabled: bool
    has_config: bool
    masked_target: str | None = None
    events: list[str]
    min_severity: str
    suppression_minutes: int
    updated_at: datetime


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    incident_id: uuid.UUID | None = None
    channel: str
    event_type: str
    dedup_key: str
    status: str
    attempt_count: int
    error_message: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


class NotificationTestRequest(BaseModel):
    channel: NotificationChannel
