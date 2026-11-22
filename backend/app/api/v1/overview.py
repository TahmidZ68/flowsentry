from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, require_workspace_role
from app.db.session import get_db
from app.models.incidents import Incident
from app.models.monitoring import Execution, Workflow
from app.models.outcomes import OutcomeMonitor
from app.schemas.monitoring import ExecutionRead, IncidentRead, OverviewMetricsRead, TrendPoint

router = APIRouter(prefix="/workspaces/{workspace_id}/overview", tags=["Overview"])


@router.get("", response_model=OverviewMetricsRead)
def get_overview(
    ctx: WorkspaceContext = Depends(require_workspace_role("viewer")),
    db: Session = Depends(get_db),
) -> OverviewMetricsRead:
    ws_id = ctx.workspace.id
    active_statuses = ("open", "acknowledged", "investigating", "reopened")

    total_workflows = int(db.scalar(select(func.count(Workflow.id)).where(Workflow.workspace_id == ws_id)) or 0)
    workflows_with_active_incidents = int(
        db.scalar(
            select(func.count(func.distinct(Incident.workflow_id))).where(
                Incident.workspace_id == ws_id,
                Incident.status.in_(active_statuses),
            )
        )
        or 0
    )
    healthy_workflows = max(0, total_workflows - workflows_with_active_incidents)

    exec_stats = db.execute(
        select(
            func.count(Execution.id),
            func.coalesce(func.sum(case((Execution.status == "success", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Execution.status == "failed", 1), else_=0)), 0),
        ).where(Execution.workspace_id == ws_id)
    ).one()
    total_executions = int(exec_stats[0] or 0)
    successful_executions = int(exec_stats[1] or 0)
    failed_executions = int(exec_stats[2] or 0)

    active_incidents = int(
        db.scalar(
            select(func.count(Incident.id)).where(
                Incident.workspace_id == ws_id,
                Incident.status.in_(active_statuses),
            )
        )
        or 0
    )
    critical_incidents = int(
        db.scalar(
            select(func.count(Incident.id)).where(
                Incident.workspace_id == ws_id,
                Incident.status.in_(active_statuses),
                Incident.severity == "critical",
            )
        )
        or 0
    )

    monitors_total = int(
        db.scalar(select(func.count(OutcomeMonitor.id)).where(OutcomeMonitor.workspace_id == ws_id)) or 0
    )
    monitors_failing = int(
        db.scalar(
            select(func.count(OutcomeMonitor.id)).where(
                OutcomeMonitor.workspace_id == ws_id,
                OutcomeMonitor.status == "failing",
            )
        )
        or 0
    )

    # 14-day execution trend computed from real Execution records
    cutoff = datetime.now(UTC) - timedelta(days=13)
    recent_for_trend = db.execute(
        select(Execution.started_at, Execution.status).where(
            Execution.workspace_id == ws_id,
            Execution.started_at >= cutoff.replace(hour=0, minute=0, second=0, microsecond=0),
        )
    ).all()

    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0})
    for started_at, st in recent_for_trend:
        day_key = started_at.strftime("%Y-%m-%d")
        buckets[day_key]["total"] += 1
        if st == "success":
            buckets[day_key]["success"] += 1
        elif st == "failed":
            buckets[day_key]["failed"] += 1

    trends: list[TrendPoint] = []
    for offset in range(13, -1, -1):
        day = (datetime.now(UTC) - timedelta(days=offset)).strftime("%Y-%m-%d")
        b = buckets[day]
        trends.append(TrendPoint(date=day, total=b["total"], success=b["success"], failed=b["failed"]))

    inc_rows = db.execute(
        select(Incident, Workflow.name)
        .join(Workflow, Workflow.id == Incident.workflow_id)
        .where(Incident.workspace_id == ws_id)
        .order_by(Incident.last_seen_at.desc())
        .limit(5)
    ).all()
    recent_incidents = [
        IncidentRead(
            id=inc.id,
            workspace_id=inc.workspace_id,
            workflow_id=inc.workflow_id,
            workflow_name=wf_name,
            title=inc.title,
            description=inc.description,
            severity=inc.severity,
            status=inc.status,
            fingerprint=inc.fingerprint,
            first_seen_at=inc.first_seen_at,
            last_seen_at=inc.last_seen_at,
            occurrence_count=inc.occurrence_count,
            assigned_to_user_id=inc.assigned_to_user_id,
            resolved_at=inc.resolved_at,
            resolution_reason=inc.resolution_reason,
            resolution_notes=inc.resolution_notes,
            is_demo=inc.is_demo,
            created_at=inc.created_at,
        )
        for inc, wf_name in inc_rows
    ]

    exec_rows = list(
        db.scalars(
            select(Execution).where(Execution.workspace_id == ws_id).order_by(Execution.started_at.desc()).limit(8)
        ).all()
    )

    return OverviewMetricsRead(
        total_workflows=total_workflows,
        healthy_workflows=healthy_workflows,
        total_executions=total_executions,
        successful_executions=successful_executions,
        failed_executions=failed_executions,
        active_incidents=active_incidents,
        critical_incidents=critical_incidents,
        monitors_total=monitors_total,
        monitors_failing=monitors_failing,
        trends=trends,
        recent_incidents=recent_incidents,
        recent_executions=[ExecutionRead.model_validate(e) for e in exec_rows],
    )
