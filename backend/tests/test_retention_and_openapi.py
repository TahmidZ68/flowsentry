from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.identity import Project, User, Workspace
from app.models.monitoring import Execution, Integration, Workflow
from app.workers.tasks import cleanup_expired_records


def test_openapi_schema_generated(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == "FlowSentry"
    paths = spec["paths"]
    assert "/api/v1/workspaces" in paths
    assert "/api/v1/workspaces/{workspace_id}/incidents" in paths
    assert "/api/v1/workspaces/{workspace_id}/outcome-monitors" in paths
    assert "/api/v1/workspaces/{workspace_id}/notifications" in paths


def test_retention_cleanup_prunes_old_executions(db_session, monkeypatch) -> None:
    owner = User(id=uuid.uuid4(), email="ret@acme.dev", name="Retention")
    db_session.add(owner)
    db_session.flush()

    ws = Workspace(name="Ret WS", slug="ret-ws", owner_id=owner.id, plan="free")
    db_session.add(ws)
    db_session.flush()

    proj = Project(workspace_id=ws.id, name="Prod", environment="production")
    db_session.add(proj)
    db_session.flush()

    integ = Integration(
        workspace_id=ws.id,
        project_id=proj.id,
        provider="custom_webhook",
        connection_name="Hook",
        encrypted_credentials="{}",
        status="connected",
    )
    db_session.add(integ)
    db_session.flush()

    wf = Workflow(
        workspace_id=ws.id,
        project_id=proj.id,
        integration_id=integ.id,
        external_workflow_id="wf-ret",
        name="Retention WF",
    )
    db_session.add(wf)
    db_session.flush()

    now = datetime.now(UTC)
    old_exec = Execution(
        workspace_id=ws.id,
        workflow_id=wf.id,
        external_execution_id="old-1",
        status="success",
        started_at=now - timedelta(days=45),
    )
    fresh_exec = Execution(
        workspace_id=ws.id,
        workflow_id=wf.id,
        external_execution_id="fresh-1",
        status="success",
        started_at=now - timedelta(days=5),
    )
    db_session.add_all([old_exec, fresh_exec])
    db_session.commit()

    class _SessionCtx:
        def __enter__(self):
            return db_session

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.workers.tasks.SessionLocal", lambda: _SessionCtx())
    res = cleanup_expired_records()
    assert res["deleted_executions"] == 1

    remaining = list(db_session.scalars(select(Execution.external_execution_id)).all())
    assert remaining == ["fresh-1"]
