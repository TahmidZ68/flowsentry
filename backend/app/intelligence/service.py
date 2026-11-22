from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.plans import get_plan_limits
from app.integrations.normalizer import sanitize_payload
from app.intelligence.providers import (
    AIProviderError,
    DeterministicFallbackAnalyzer,
    ProviderResult,
    resolve_ai_provider,
)
from app.models.identity import UsageRecord, Workspace
from app.models.incidents import AIInvestigation, Incident, IncidentOccurrence
from app.models.monitoring import Execution, Workflow
from app.services.audit_service import record_audit_log
from app.services.usage_service import current_period_month

logger = logging.getLogger("flowsentry.intelligence")


def build_sanitized_evidence(db: Session, *, incident: Incident) -> dict[str, Any]:
    workflow = db.get(Workflow, incident.workflow_id)
    executions = list(
        db.scalars(
            select(Execution)
            .join(IncidentOccurrence, IncidentOccurrence.execution_id == Execution.id)
            .where(IncidentOccurrence.incident_id == incident.id)
            .order_by(Execution.started_at.desc())
            .limit(5)
        ).all()
    )
    prior_incidents_count = int(
        db.scalar(
            select(func.count(Incident.id)).where(
                Incident.workspace_id == incident.workspace_id,
                Incident.workflow_id == incident.workflow_id,
                Incident.id != incident.id,
            )
        )
        or 0
    )

    recent_exec_evidence = [
        {
            "external_execution_id": ex.external_execution_id,
            "status": ex.status,
            "started_at": ex.started_at.isoformat(),
            "duration_ms": ex.duration_ms,
            "failed_node": ex.failed_node,
            "error_type": ex.error_type,
            "error_summary": ex.error_summary,
            "metadata": sanitize_payload((ex.normalized_payload or {}).get("metadata", {})),
        }
        for ex in executions
    ]

    inferred_error_type = recent_exec_evidence[0]["error_type"] if recent_exec_evidence else None
    if not inferred_error_type and "SILENT_FAILURE" in incident.title.upper():
        inferred_error_type = "SILENT_FAILURE"

    return {
        "incident": {
            "id": str(incident.id),
            "title": incident.title,
            "description": incident.description,
            "severity": incident.severity,
            "status": incident.status,
            "occurrence_count": incident.occurrence_count,
            "first_seen_at": incident.first_seen_at.isoformat(),
            "last_seen_at": incident.last_seen_at.isoformat(),
            "workflow_name": workflow.name if workflow else "Unknown Workflow",
            "error_type": inferred_error_type,
        },
        "recent_executions": recent_exec_evidence,
        "prior_incidents_count": prior_incidents_count,
    }


def _check_and_consume_ai_quota(db: Session, *, workspace: Workspace) -> bool:
    """Return True if workspace has AI quota remaining; consumes 1 slot if available."""
    if workspace.is_demo:
        return True
    period = current_period_month()
    limits = get_plan_limits(workspace.plan)
    usage = db.scalar(
        select(UsageRecord).where(
            UsageRecord.workspace_id == workspace.id,
            UsageRecord.period_month == period,
        )
    )
    current_ai = usage.ai_investigations_count if usage else 0
    if current_ai >= limits.max_monthly_ai_investigations:
        return False

    if usage is None:
        usage = UsageRecord(
            workspace_id=workspace.id,
            period_month=period,
            executions_count=0,
            ai_investigations_count=1,
            ai_tokens_used=0,
        )
        db.add(usage)
    else:
        usage.ai_investigations_count += 1
    db.flush()
    return True


def _record_ai_tokens(db: Session, *, workspace_id: uuid.UUID, total_tokens: int) -> None:
    if total_tokens <= 0:
        return
    period = current_period_month()
    usage = db.scalar(
        select(UsageRecord).where(
            UsageRecord.workspace_id == workspace_id,
            UsageRecord.period_month == period,
        )
    )
    if usage is not None:
        usage.ai_tokens_used += total_tokens


def execute_investigation(
    db: Session,
    *,
    investigation: AIInvestigation,
    workspace: Workspace,
    incident: Incident,
    transport: httpx.BaseTransport | None = None,
) -> AIInvestigation:
    evidence_payload = build_sanitized_evidence(db, incident=incident)
    provider = resolve_ai_provider(transport=transport)
    fallback = DeterministicFallbackAnalyzer()

    result: ProviderResult | None = None
    fallback_reason: str | None = None

    if provider is not None:
        if _check_and_consume_ai_quota(db, workspace=workspace):
            for attempt in range(2):
                try:
                    result = provider.analyze(evidence_payload)
                    break
                except AIProviderError as exc:
                    fallback_reason = str(exc)
                    logger.warning("AI provider attempt %d failed: %s", attempt + 1, exc)
                    if attempt == 0:
                        time.sleep(0.2)
        else:
            fallback_reason = "Monthly AI investigation quota exceeded; used deterministic fallback"

    if result is None:
        result = fallback.analyze(evidence_payload)
        investigation.analysis_status = "completed_fallback" if fallback_reason else "completed"
        investigation.error_message = fallback_reason
    else:
        investigation.analysis_status = "completed"
        investigation.error_message = None
        _record_ai_tokens(
            db,
            workspace_id=workspace.id,
            total_tokens=result.token_usage.get("total_tokens", 0),
        )

    investigation.provider = result.provider
    investigation.model = result.model
    investigation.summary = result.output.summary
    investigation.root_cause_hypothesis = result.output.root_cause_hypothesis
    investigation.confidence = Decimal(str(round(result.output.confidence, 3)))
    investigation.evidence = result.output.evidence
    investigation.possible_causes = result.output.possible_causes
    investigation.recommended_actions = result.output.recommended_actions
    investigation.severity_assessment = result.output.severity_assessment
    investigation.requires_human_review = result.output.requires_human_review
    investigation.token_usage = result.token_usage
    investigation.completed_at = datetime.now(UTC)

    db.commit()
    db.refresh(investigation)
    return investigation


def start_investigation(
    db: Session,
    *,
    workspace: Workspace,
    incident: Incident,
    actor_id: uuid.UUID,
    run_async: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> AIInvestigation:
    investigation = AIInvestigation(
        incident_id=incident.id,
        workspace_id=workspace.id,
        provider="pending",
        model="pending",
        analysis_status="queued",
    )
    db.add(investigation)
    db.flush()

    record_audit_log(
        db,
        workspace_id=workspace.id,
        user_id=actor_id,
        action="investigation.started",
        resource_type="ai_investigation",
        resource_id=investigation.id,
        metadata={"incident_id": str(incident.id)},
    )
    db.commit()
    db.refresh(investigation)

    if run_async:
        try:
            from app.workers.tasks import run_ai_investigation_task

            run_ai_investigation_task.delay(str(investigation.id))
            return investigation
        except Exception as exc:
            logger.warning("Celery broker unavailable; executing investigation inline: %s", exc)

    return execute_investigation(
        db,
        investigation=investigation,
        workspace=workspace,
        incident=incident,
        transport=transport,
    )
