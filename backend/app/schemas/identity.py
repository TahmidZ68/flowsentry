from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")

WorkspaceRole = Literal["owner", "admin", "member", "viewer"]
ProjectEnvironment = Literal["production", "staging", "development"]


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Any | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str | None = None
    avatar_url: str | None = None
    created_at: datetime


class DevTokenRequest(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=120)


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, min_length=2, max_length=120, pattern=r"^[a-z0-9-]+$")


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    settings: dict[str, Any] | None = None


class PlanLimitsRead(BaseModel):
    name: str
    display_name: str
    price_monthly_usd: int
    max_projects: int
    max_integrations: int
    max_monthly_executions: int
    max_monthly_ai_investigations: int
    max_outcome_monitors: int
    max_members: int
    retention_days: int


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    owner_id: uuid.UUID
    plan: str
    is_demo: bool
    settings: dict[str, Any]
    role: WorkspaceRole | None = None
    created_at: datetime


class AuthMeResponse(BaseModel):
    user: UserRead
    workspaces: list[WorkspaceRead]


class WorkspaceMemberAdd(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "viewer"] = "member"


class WorkspaceMemberUpdate(BaseModel):
    role: Literal["admin", "member", "viewer"]


class WorkspaceMemberRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    email: EmailStr
    name: str | None = None
    role: WorkspaceRole
    joined_at: datetime


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    environment: ProjectEnvironment = "production"


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    environment: ProjectEnvironment | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None = None
    environment: str
    created_at: datetime


class APIKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["ingest:write"])


class APIKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class APIKeyCreateResponse(BaseModel):
    api_key: APIKeyRead
    plaintext_key: str


class UsageSummaryRead(BaseModel):
    workspace_id: uuid.UUID
    period_month: str
    plan: PlanLimitsRead
    executions_count: int
    ai_investigations_count: int
    ai_tokens_used: int
    projects_count: int
    integrations_count: int
    outcome_monitors_count: int
    members_count: int


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    metadata_json: dict[str, Any]
    created_at: datetime
