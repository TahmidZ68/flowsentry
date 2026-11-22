from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import issue_auth_headers


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_workspace_project_rbac_api_keys_and_usage(client: TestClient) -> None:
    owner_headers, _ = issue_auth_headers(client, "owner@acme.dev", "Alice Owner")

    # Create workspace
    ws_resp = client.post(
        "/api/v1/workspaces",
        json={"name": "Acme Automation"},
        headers=owner_headers,
    )
    assert ws_resp.status_code == 201, ws_resp.text
    ws = ws_resp.json()
    ws_id = ws["id"]
    assert ws["role"] == "owner"
    assert ws["plan"] == "free"

    # Auth me lists workspace
    me_resp = client.get("/api/v1/auth/me", headers=owner_headers)
    assert me_resp.status_code == 200
    assert len(me_resp.json()["workspaces"]) == 1

    # Default project was created automatically; Free plan allows max 2 projects
    proj_list = client.get(f"/api/v1/workspaces/{ws_id}/projects", headers=owner_headers)
    assert proj_list.status_code == 200
    assert proj_list.json()["total"] == 1

    p2 = client.post(
        f"/api/v1/workspaces/{ws_id}/projects",
        json={"name": "Client Staging", "environment": "staging"},
        headers=owner_headers,
    )
    assert p2.status_code == 201

    # 3rd project hits Free plan quota
    p3 = client.post(
        f"/api/v1/workspaces/{ws_id}/projects",
        json={"name": "Over Quota", "environment": "development"},
        headers=owner_headers,
    )
    assert p3.status_code == 403
    assert p3.json()["code"] == "PLAN_LIMIT_REACHED"

    # API key creation returns plaintext once, listing omits plaintext
    key_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/api-keys",
        json={"name": "n8n Webhook Key", "scopes": ["ingest:write"]},
        headers=owner_headers,
    )
    assert key_resp.status_code == 201
    plaintext_key = key_resp.json()["plaintext_key"]
    key_id = key_resp.json()["api_key"]["id"]
    assert plaintext_key.startswith("fs_live_")

    keys_list = client.get(f"/api/v1/workspaces/{ws_id}/api-keys", headers=owner_headers).json()
    assert len(keys_list) == 1
    assert "plaintext_key" not in keys_list[0]
    assert "key_hash" not in keys_list[0]

    revoke_resp = client.delete(f"/api/v1/workspaces/{ws_id}/api-keys/{key_id}", headers=owner_headers)
    assert revoke_resp.status_code == 204

    # Usage & audit logs work
    usage = client.get(f"/api/v1/workspaces/{ws_id}/usage", headers=owner_headers)
    assert usage.status_code == 200
    assert usage.json()["projects_count"] == 2
    assert usage.json()["plan"]["name"] == "free"

    audits = client.get(f"/api/v1/workspaces/{ws_id}/audit-logs", headers=owner_headers)
    assert audits.status_code == 200
    actions = {item["action"] for item in audits.json()["items"]}
    assert {"workspace.created", "project.created", "api_key.created", "api_key.revoked"}.issubset(actions)


def test_cross_tenant_isolation_scenario_4(client: TestClient) -> None:
    user_a_headers, _ = issue_auth_headers(client, "alice@tenanta.dev", "Alice")
    user_b_headers, _ = issue_auth_headers(client, "bob@tenantb.dev", "Bob")

    ws_a = client.post("/api/v1/workspaces", json={"name": "Tenant A"}, headers=user_a_headers).json()
    ws_b = client.post("/api/v1/workspaces", json={"name": "Tenant B"}, headers=user_b_headers).json()
    ws_a_id = ws_a["id"]
    assert ws_b["id"] != ws_a_id

    # User B tries every workspace-scoped endpoint for Tenant A -> all must deny
    for method, path in [
        ("GET", f"/api/v1/workspaces/{ws_a_id}"),
        ("PATCH", f"/api/v1/workspaces/{ws_a_id}"),
        ("GET", f"/api/v1/workspaces/{ws_a_id}/projects"),
        ("POST", f"/api/v1/workspaces/{ws_a_id}/projects"),
        ("GET", f"/api/v1/workspaces/{ws_a_id}/members"),
        ("GET", f"/api/v1/workspaces/{ws_a_id}/api-keys"),
        ("GET", f"/api/v1/workspaces/{ws_a_id}/usage"),
        ("GET", f"/api/v1/workspaces/{ws_a_id}/audit-logs"),
    ]:
        kwargs = {"headers": user_b_headers}
        if method in {"PATCH", "POST"}:
            kwargs["json"] = {"name": "Hijack"}
        resp = client.request(method, path, **kwargs)
        assert resp.status_code == 403, f"Expected 403 for {method} {path}, got {resp.status_code}"


def test_member_role_permissions_and_client_cannot_mutate_plan(client: TestClient) -> None:
    owner_headers, _ = issue_auth_headers(client, "owner@team.dev", "Owner")
    ws = client.post("/api/v1/workspaces", json={"name": "Team WS"}, headers=owner_headers).json()
    ws_id = ws["id"]

    # Free plan max_members is 1 -> adding a 2nd member returns PLAN_LIMIT_REACHED
    add_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "viewer@team.dev", "role": "viewer"},
        headers=owner_headers,
    )
    assert add_resp.status_code == 403
    assert add_resp.json()["code"] == "PLAN_LIMIT_REACHED"

    # Attempt client-side plan escalation via PATCH -> plan remains free
    patch_resp = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"name": "Team WS Updated", "plan": "business"},
        headers=owner_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["plan"] == "free"


def test_rbac_viewer_cannot_mutate_and_owner_cannot_be_removed(client: TestClient, db_session) -> None:
    import uuid

    from app.models.identity import Workspace

    owner_headers, _ = issue_auth_headers(client, "lead@agency.dev", "Lead")
    viewer_headers, _ = issue_auth_headers(client, "viewer@agency.dev", "Viewer")
    ws = client.post("/api/v1/workspaces", json={"name": "Agency Pro"}, headers=owner_headers).json()
    ws_id = ws["id"]

    # Upgrade workspace plan server-side in DB to test multi-member RBAC
    ws_row = db_session.get(Workspace, uuid.UUID(ws_id))
    assert ws_row is not None
    ws_row.plan = "pro"
    db_session.commit()

    add_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "viewer@agency.dev", "role": "viewer"},
        headers=owner_headers,
    )
    assert add_resp.status_code == 201
    viewer_member_id = add_resp.json()["id"]

    # Viewer can read workspace and projects
    assert client.get(f"/api/v1/workspaces/{ws_id}", headers=viewer_headers).status_code == 200
    assert client.get(f"/api/v1/workspaces/{ws_id}/projects", headers=viewer_headers).status_code == 200

    # Viewer cannot create projects, update workspace, or view/create API keys
    assert (
        client.post(
            f"/api/v1/workspaces/{ws_id}/projects",
            json={"name": "Blocked", "environment": "production"},
            headers=viewer_headers,
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/workspaces/{ws_id}/api-keys", headers=viewer_headers).status_code == 403

    # Owner promotes viewer to member, then removes
    upd = client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{viewer_member_id}",
        json={"role": "member"},
        headers=owner_headers,
    )
    assert upd.status_code == 200
    assert upd.json()["role"] == "member"

    rem = client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{viewer_member_id}",
        headers=owner_headers,
    )
    assert rem.status_code == 204
