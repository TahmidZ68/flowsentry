# FlowSentry — Security Architecture & Controls

## 1. Authentication & Authorization
- **JWT Verification:** FastAPI validates Bearer tokens using Supabase's JWKS endpoint (`RS256` / `ES256`) or `HS256` (`SUPABASE_JWT_SECRET`). `AUTH_MODE=local_dev` is strictly rejected when `ENVIRONMENT=production`.
- **Multi-Tenant Isolation:** Every workspace-owned database query scopes by `workspace_id`. `require_workspace_role(min_role)` validates `workspace_members` membership and enforces `owner > admin > member > viewer`. Knowing a UUID never grants cross-workspace access.

## 2. Credential & Secret Protection
- **Encryption at Rest:** Integration API keys and notification configs (Slack webhooks, email recipients) are encrypted using authenticated Fernet encryption (`ENCRYPTION_KEY`) before database storage.
- **Zero Secret Leakage:** Decrypted credentials are never returned by API endpoints. Notification endpoints return masked targets (`https://hooks.slack.com/...****`). Disconnecting an integration scrubs `encrypted_credentials` and `webhook_secret_hash`.
- **Log & Payload Scrubbing:** Structured JSON logs and execution payload sanitizers redact `Authorization`, `X-N8N-API-KEY`, cookies, passwords, API keys, and JWT/Bearer patterns before persistence or AI analysis.

## 3. Outbound Network & SSRF Protections
- `validate_outbound_url()` checks scheme (`http`/`https` only), rejects embedded URL credentials, resolves DNS, and blocks loopback (`127.0.0.0/8`, `::1`), RFC1918 private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local/cloud metadata (`169.254.0.0/16`, `metadata.google.internal`), and disables automatic redirects on outbound integration/outcome/Slack HTTP requests.

## 4. API & Webhook Hardening
- Redis-backed fixed-window rate limiting on auth, webhook ingestion, and direct ingestion endpoints.
- Strict CORS origin allowlist (`ALLOWED_ORIGINS`) with explicit allowed methods and headers.
- Security response headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`).
- Immutable `audit_logs` for workspace, member, project, integration, API key, outcome monitor, notification, and incident state mutations.
