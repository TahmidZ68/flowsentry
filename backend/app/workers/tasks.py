from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.detection.engine import _ensure_utc, _upsert_incident
from app.intelligence.service import execute_investigation
from app.models.identity import Workspace
from app.models.incidents import AIInvestigation, Incident
from app.models.monitoring import Execution, Integration, Workflow
from app.models.outcomes import OutcomeMonitor
from app.outcomes.service import evaluate_monitor
from app.services.integration_service import sync_n8n_integration
from app.workers.celery_app import celery_app

logger = logging.getLogger("flowsentry.workers")


@celery_app.task(name="flowsentry.sync_integration")
def sync_integration_task(integration_id: str) -> dict[str, int | str]:
    with SessionLocal() as db:
        integration = db.get(Integration, uuid.UUID(integration_id))
        if integration is None or integration.status == "disconnected":
            return {"status": "skipped"}
        workspace = db.get(Workspace, integration.workspace_id)
        if workspace is None:
            return {"status": "skipped"}
        result = sync_n8n_integration(db, workspace=workspace, integration_id=integration.id)
        return {
            "status": "ok",
            "workflows_synced": result.workflows_synced,
            "executions_ingested": result.executions_ingested,
        }


@celery_app.task(name="flowsentry.poll_enabled_integrations")
def poll_enabled_integrations() -> dict[str, int]:
    polled = 0
    errors = 0
    with SessionLocal() as db:
        integrations = list(
            db.scalars(
                select(Integration).where(
                    Integration.provider == "n8n",
                    Integration.polling_enabled.is_(True),
                    Integration.status.in_(("connected", "pending")),
                )
            ).all()
        )
        for integration in integrations:
            workspace = db.get(Workspace, integration.workspace_id)
            if workspace is None:
                continue
            try:
                sync_n8n_integration(db, workspace=workspace, integration_id=integration.id)
                polled += 1
            except Exception as exc:
                errors += 1
                logger.warning("Polling integration %s failed: %s", integration.id, exc)
    return {"polled": polled, "errors": errors}


@celery_app.task(name="flowsentry.run_ai_investigation")
def run_ai_investigation_task(investigation_id: str) -> dict[str, str]:
    with SessionLocal() as db:
        investigation = db.get(AIInvestigation, uuid.UUID(investigation_id))
        if investigation is None:
            return {"status": "not_found"}
        workspace = db.get(Workspace, investigation.workspace_id)
        incident = db.get(Incident, investigation.incident_id)
        if workspace is None or incident is None:
            return {"status": "missing_parent"}
        execute_investigation(
            db,
            investigation=investigation,
            workspace=workspace,
            incident=incident,
        )
        return {"status": investigation.analysis_status}


@celery_app.task(name="flowsentry.evaluate_due_outcome_monitors")
def evaluate_due_outcome_monitors() -> dict[str, int]:
    evaluated = 0
    failed = 0
    now = datetime.now(UTC)
    with SessionLocal() as db:
        monitors = list(db.scalars(select(OutcomeMonitor).where(OutcomeMonitor.enabled.is_(True))).all())
        for monitor in monitors:
            if monitor.last_checked_at is not None:
                due_at = _ensure_utc(monitor.last_checked_at) + timedelta(seconds=monitor.schedule_seconds)
                if due_at > now:
                    continue
            workspace = db.get(Workspace, monitor.workspace_id)
            if workspace is None:
                continue
            run, _ = evaluate_monitor(db, workspace=workspace, monitor=monitor)
            evaluated += 1
            if not run.passed:
                failed += 1
    return {"evaluated": evaluated, "failed": failed}


@celery_app.task(name="flowsentry.evaluate_frequency_anomalies")
def evaluate_frequency_anomalies() -> dict[str, int]:
    checked = 0
    flagged = 0
    now = datetime.now(UTC)
    with SessionLocal() as db:
        workflows = list(
            db.scalars(
                select(Workflow).where(
                    Workflow.enabled.is_(True),
                    Workflow.expected_interval_seconds.is_not(None),
                )
            ).all()
        )
        for wf in workflows:
            checked += 1
            latest = db.scalar(
                select(Execution.started_at)
                .where(Execution.workflow_id == wf.id)
                .order_by(Execution.started_at.desc())
                .limit(1)
            )
            if latest is None:
                continue
            elapsed = (now - _ensure_utc(latest)).total_seconds()
            if wf.expected_interval_seconds and elapsed > wf.expected_interval_seconds:
                workspace = db.get(Workspace, wf.workspace_id)
                if workspace is None:
                    continue
                msg = (
                    f"Workflow has not executed in {int(elapsed)}s "
                    f"(expected at least every {wf.expected_interval_seconds}s)"
                )
                _upsert_incident(
                    db,
                    workspace=workspace,
                    workflow=wf,
                    execution=None,
                    title=f"{wf.name}: Missed scheduled execution",
                    description=msg,
                    error_type="FREQUENCY_ANOMALY",
                    failed_node="Scheduler",
                    error_message=msg,
                    event_time=now,
                )
                flagged += 1
        db.commit()
    return {"checked": checked, "flagged": flagged}
