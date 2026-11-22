from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.encryption import encrypt_json
from app.detection.engine import compute_incident_fingerprint
from app.models.identity import Project, User, Workspace, WorkspaceMember
from app.models.incidents import AIInvestigation, Incident, IncidentNote, IncidentOccurrence
from app.models.monitoring import Execution, ExecutionEvent, Integration, Workflow
from app.models.outcomes import OutcomeMonitor, OutcomeMonitorRun


def seed_or_reset_demo_workspace(db: Session, *, owner: User) -> Workspace:
    """
    Create or cleanly reset an isolated demo workspace (is_demo=True).
    Demo data is strictly isolated from production customer workspaces.
    """
    demo_slug = f"demo-{str(owner.id)[:8]}"
    existing = db.scalar(select(Workspace).where(Workspace.slug == demo_slug, Workspace.is_demo.is_(True)))
    if existing is not None:
        # Delete and recreate clean demo dataset
        db.execute(delete(Workspace).where(Workspace.id == existing.id))
        db.flush()

    now = datetime.now(UTC)
    ws = Workspace(
        name="FlowSentry Demo Sandbox",
        slug=demo_slug,
        owner_id=owner.id,
        plan="agency",
        is_demo=True,
        settings={"grouping_window_hours": 24, "recovery_consecutive_successes": 3},
    )
    db.add(ws)
    db.flush()

    db.add(WorkspaceMember(workspace_id=ws.id, user_id=owner.id, role="owner"))
    proj = Project(
        workspace_id=ws.id,
        name="Demo Agency Automations",
        description="Isolated demo dataset — safe to reset anytime",
        environment="production",
    )
    db.add(proj)
    db.flush()

    integration = Integration(
        workspace_id=ws.id,
        project_id=proj.id,
        provider="n8n",
        connection_name="Demo n8n Instance",
        base_url="https://demo-n8n.flowsentry.local",
        encrypted_credentials=encrypt_json({"demo": True}),
        polling_enabled=False,
        status="connected",
        last_connected_at=now,
        last_synced_at=now,
    )
    db.add(integration)
    db.flush()

    wf_leads = Workflow(
        workspace_id=ws.id,
        project_id=proj.id,
        integration_id=integration.id,
        external_workflow_id="demo-wf-leads",
        name="[DEMO] Inbound Lead to HubSpot CRM",
        description="Captures Typeform leads and creates HubSpot contacts",
        enabled=True,
        is_demo=True,
    )
    wf_invoices = Workflow(
        workspace_id=ws.id,
        project_id=proj.id,
        integration_id=integration.id,
        external_workflow_id="demo-wf-invoices",
        name="[DEMO] Stripe Payment to Invoice PDF",
        description="Generates customer invoices on checkout completion",
        enabled=True,
        is_demo=True,
    )
    db.add_all([wf_leads, wf_invoices])
    db.flush()

    # Sample healthy runs + 2 grouped HTTP 429 failures
    for i in range(4):
        t = now - timedelta(hours=6 - i)
        db.add(
            Execution(
                workspace_id=ws.id,
                workflow_id=wf_invoices.id,
                external_execution_id=f"demo-inv-ok-{i}",
                status="success",
                started_at=t,
                finished_at=t + timedelta(milliseconds=840),
                duration_ms=840,
                normalized_payload={"metadata": {"invoice_created": True, "demo": True}},
                is_demo=True,
            )
        )

    fail_execs: list[Execution] = []
    for idx in range(2):
        t = now - timedelta(minutes=25 - idx * 10)
        ex = Execution(
            workspace_id=ws.id,
            workflow_id=wf_leads.id,
            external_execution_id=f"demo-lead-err-{idx}",
            status="failed",
            started_at=t,
            finished_at=t + timedelta(milliseconds=1450),
            duration_ms=1450,
            failed_node="Create HubSpot Contact",
            error_type="HTTP_429",
            error_summary="HTTP 429 Too Many Requests: HubSpot API burst limit exceeded",
            normalized_payload={"metadata": {"mode": "webhook", "demo": True}},
            is_demo=True,
        )
        db.add(ex)
        fail_execs.append(ex)
    db.flush()

    for ex in fail_execs:
        db.add(
            ExecutionEvent(
                execution_id=ex.id,
                event_type="execution.failed",
                node_name="Create HubSpot Contact",
                event_timestamp=ex.finished_at or ex.started_at,
                event_payload={"error_type": "HTTP_429", "demo": True},
            )
        )

    fp = compute_incident_fingerprint(
        workspace_id=ws.id,
        workflow_id=wf_leads.id,
        error_type="HTTP_429",
        failed_node="Create HubSpot Contact",
        error_message="HTTP 429 Too Many Requests: HubSpot API burst limit exceeded",
    )
    inc = Incident(
        workspace_id=ws.id,
        workflow_id=wf_leads.id,
        title="[DEMO] Inbound Lead to HubSpot CRM: HTTP_429 at node 'Create HubSpot Contact'",
        description="HTTP 429 Too Many Requests: HubSpot API burst limit exceeded",
        severity="high",
        status="open",
        fingerprint=fp,
        grouping_window_expires_at=now + timedelta(hours=24),
        first_seen_at=fail_execs[0].started_at,
        last_seen_at=fail_execs[-1].started_at,
        occurrence_count=2,
        is_demo=True,
    )
    db.add(inc)
    db.flush()

    for ex in fail_execs:
        db.add(IncidentOccurrence(incident_id=inc.id, execution_id=ex.id))

    db.add(
        IncidentNote(
            incident_id=inc.id,
            workspace_id=ws.id,
            note_type="system",
            content="Demo incident seeded for evaluation.",
        )
    )

    db.add(
        AIInvestigation(
            incident_id=inc.id,
            workspace_id=ws.id,
            provider="deterministic",
            model="rule-engine-v1",
            analysis_status="completed",
            summary="Workflow '[DEMO] Inbound Lead to HubSpot CRM' failed due to HubSpot API rate limiting (HTTP 429).",
            root_cause_hypothesis=(
                "Concurrent lead bursts exceeded the HubSpot CRM API burst limit at 'Create HubSpot Contact'."
            ),
            confidence=Decimal("0.860"),
            evidence=[
                "Observed HTTP 429 Too Many Requests on node 'Create HubSpot Contact'.",
                "Incident grouped 2 occurrences within 15 minutes.",
            ],
            possible_causes=[
                "Burst webhook traffic without node-level retry/backoff.",
                "Shared HubSpot API key hitting rate ceiling.",
            ],
            recommended_actions=[
                "Enable Retry On Fail with exponential backoff in n8n on 'Create HubSpot Contact'.",
                "Batch high-volume lead imports with a Split In Batches + Wait node.",
            ],
            severity_assessment="high",
            requires_human_review=True,
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            completed_at=now,
        )
    )

    monitor = OutcomeMonitor(
        workspace_id=ws.id,
        workflow_id=wf_invoices.id,
        name="[DEMO] Invoice Output Field Verification",
        description="Verifies invoice_created metadata is present after Stripe payment runs",
        monitor_type="required_output_fields",
        configuration={"required_fields": ["metadata.invoice_created"]},
        expected_result={"required_fields": ["metadata.invoice_created"]},
        schedule_seconds=300,
        severity="high",
        enabled=True,
        status="healthy",
        last_checked_at=now,
        last_success_at=now,
        is_demo=True,
    )
    db.add(monitor)
    db.flush()

    db.add(
        OutcomeMonitorRun(
            monitor_id=monitor.id,
            workspace_id=ws.id,
            passed=True,
            evidence={"verified": True, "demo": True},
            duration_ms=12,
            checked_at=now,
        )
    )

    db.commit()
    db.refresh(ws)
    return ws
