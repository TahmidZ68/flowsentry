from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.plans import get_plan_limits
from app.models.identity import Project, UsageRecord, Workspace, WorkspaceMember
from app.models.monitoring import Integration
from app.models.outcomes import OutcomeMonitor
from app.schemas.identity import PlanLimitsRead, UsageSummaryRead


def current_period_month() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def get_workspace_usage_summary(db: Session, *, workspace: Workspace) -> UsageSummaryRead:
    period = current_period_month()
    usage = db.scalar(
        select(UsageRecord).where(
            UsageRecord.workspace_id == workspace.id,
            UsageRecord.period_month == period,
        )
    )
    limits = get_plan_limits(workspace.plan)

    projects_count = db.scalar(select(func.count(Project.id)).where(Project.workspace_id == workspace.id)) or 0
    integrations_count = (
        db.scalar(
            select(func.count(Integration.id)).where(
                Integration.workspace_id == workspace.id,
                Integration.status != "disconnected",
            )
        )
        or 0
    )
    monitors_count = (
        db.scalar(select(func.count(OutcomeMonitor.id)).where(OutcomeMonitor.workspace_id == workspace.id)) or 0
    )
    members_count = (
        db.scalar(select(func.count(WorkspaceMember.id)).where(WorkspaceMember.workspace_id == workspace.id)) or 0
    )

    return UsageSummaryRead(
        workspace_id=workspace.id,
        period_month=period,
        plan=PlanLimitsRead(
            name=limits.name,
            display_name=limits.display_name,
            price_monthly_usd=limits.price_monthly_usd,
            max_projects=limits.max_projects,
            max_integrations=limits.max_integrations,
            max_monthly_executions=limits.max_monthly_executions,
            max_monthly_ai_investigations=limits.max_monthly_ai_investigations,
            max_outcome_monitors=limits.max_outcome_monitors,
            max_members=limits.max_members,
            retention_days=limits.retention_days,
        ),
        executions_count=usage.executions_count if usage else 0,
        ai_investigations_count=usage.ai_investigations_count if usage else 0,
        ai_tokens_used=usage.ai_tokens_used if usage else 0,
        projects_count=projects_count,
        integrations_count=integrations_count,
        outcome_monitors_count=monitors_count,
        members_count=members_count,
    )
