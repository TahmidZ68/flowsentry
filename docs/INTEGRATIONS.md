# FlowSentry — Integrations Guide

## 1. n8n Integration (Primary Supported Provider)

### Supported Mechanism & API Contract
FlowSentry integrates with n8n using two complementary, officially documented mechanisms:
1. **n8n Public REST API v1 (`X-N8N-API-KEY`)**
   - Connection validation: `GET /api/v1/workflows?limit=1`
   - Workflow synchronization: `GET /api/v1/workflows` using `limit=100` and `nextCursor` pagination
   - Execution synchronization: `GET /api/v1/executions` using `limit=100`, `includeData=true`, `startedAfter`, and `nextCursor` pagination
   - Compatible with n8n v1.x+ instances with Public REST API enabled (`Settings -> n8n API`).
2. **Error Trigger Webhook Ingestion**
   - Receives outbound HTTP POST payloads from an n8n Error Workflow containing an **Error Trigger** node.
   - Authenticates via `X-FlowSentry-Webhook-Secret` (generated per integration and stored hashed).
   - Handles both array (`[{"execution": ..., "workflow": ...}]`) and single-object payloads, as well as instant unsaved trigger failures where `execution.id` is omitted.

> **Verification Status:** Tested via `httpx.MockTransport` contract tests against the documented n8n REST API v1 and Error Trigger payload schemas. Live validation against an external production n8n server requires supplying an instance URL and API key.

---

### Configuring n8n Error Trigger Workflow
1. In FlowSentry, open **Integrations** and create an **n8n** or **Webhook-Only** integration.
2. Copy the one-time `webhook_secret` and endpoint path:
   `POST https://<your-flowsentry-domain>/api/v1/ingest/webhooks/n8n/<integration_id>`
3. In n8n, create a dedicated **Error Workflow**:
   - Node 1: **Error Trigger**
   - Node 2: **HTTP Request** (`Method: POST`, `URL`: your FlowSentry webhook URL, Header `X-FlowSentry-Webhook-Secret: <your-secret>`, `Send Body: JSON`, `Body`: `={{ $json }}`).
4. In your monitored n8n workflows, open **Settings -> Error Workflow** and select the new Error Workflow.

### Security Considerations for Self-Hosted n8n
- **Do NOT expose an internal n8n instance to the public internet solely for polling.** If your n8n server is behind a firewall/NAT, select **Webhook-Only** mode so n8n pushes outbound Error Trigger events to FlowSentry over HTTPS without opening inbound ports.
- FlowSentry blocks private/loopback/cloud-metadata IPs by default (`ALLOW_PRIVATE_INTEGRATION_HOSTS=false`) to prevent SSRF attacks. Only enable `ALLOW_PRIVATE_INTEGRATION_HOSTS=true` in trusted private VPC deployments.

---

### Safe Local Testing Without External n8n
- Use the **Test Webhook** button in the **Integrations** UI (or `POST /api/v1/workspaces/{workspace_id}/integrations/{id}/test-webhook`) to send a realistic HTTP 429 Error Trigger payload through the real normalization, sanitization, and incident detection pipeline.
- Example Error Trigger payload for `curl`:
```json
{
  "execution": {
    "id": "231",
    "mode": "webhook",
    "lastNodeExecuted": "Create CRM Contact",
    "error": {
      "message": "HTTP 429 Too Many Requests: Rate limit exceeded"
    }
  },
  "workflow": {
    "id": "1",
    "name": "Lead Capture to CRM"
  }
}
```
