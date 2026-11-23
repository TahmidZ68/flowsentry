# FlowSentry — Phase 11 Security Test Results

**Assessment Date:** 2026-11-23  
**Scope:** Focused security verification across SSRF, DNS rebinding, redirects, metadata access, authentication, multi-tenant RBAC, API keys, webhooks, rate limiting, sanitization, and request limits.

---

## 1. Security Test Matrix

| Attack / Control Vector | Test Method & Scope | Expected Outcome | Observed Result | Status |
|---|---|---|---|---|
| **Cloud Metadata Access (`169.254.169.254`)** | Automated (`test_security_foundation.py`) + API integration creation (`test_integrations_and_incidents.py`) | Blocked even if `ALLOW_PRIVATE_INTEGRATION_HOSTS=true` | `SSRFValidationError` / `HTTP 422 INVALID_URL` | **PASS** |
| **IPv4-Mapped IPv6 (`::ffff:169.254.169.254`, `::ffff:127.0.0.1`)** | Automated (`test_security_foundation.py`) | Recursively unwrapped in `_validate_ip` and blocked | `SSRFValidationError` raised | **PASS** |
| **Private / Docker RFC1918 Targets** | Live API against `http://flowsentry-n8n-real:5678` (`172.20.0.6`) with `ALLOW_PRIVATE_INTEGRATION_HOSTS=false` | Rejected (`422 INVALID_URL`) | Observed `Blocked private/loopback IP target: 172.20.0.6` | **PASS** |
| **DNS Rebinding (TOCTOU)** | Controlled `_SSRFSafeSyncBackend.connect_tcp` test with mocked `socket.getaddrinfo` -> `169.254.169.254` (`test_phase11_security_and_monitors.py`) | Blocked at socket connect time before TCP connect | `SSRFValidationError` raised | **PASS** |
| **HTTP Redirect SSRF Bypass** | `_evaluate_http_check` receiving `HTTP 302 Location: http://169.254.169.254/...` (`test_phase11_security_and_monitors.py`) | `follow_redirects=False`; redirect not followed | Returned `ok=False`, `"received HTTP 302"` | **PASS** |
| **Webhook Secret Auth & Malformed Payloads** | Live API + `test_integrations_and_incidents.py` | Missing/wrong secret -> `401`; malformed body -> `422` | Verified `401` and `422` | **PASS** |
| **Webhook Replay / Duplicate Ingestion** | Live API against real n8n (`phase11_real_n8n.py`) + live E2E (`phase8_live_e2e.py`) | Duplicate `external_execution_id` returns `deduplicated=true` without double-counting | Verified `executions_deduplicated=3` | **PASS** |
| **Webhook Payload Size Cap (1 MB)** | Automated (`test_phase6_api_key_ingest_webhook_size_limit_and_request_id`) | `>1,048,576` bytes rejected with `HTTP 413` | Verified `HTTP 413 PAYLOAD_TOO_LARGE` | **PASS** |
| **API Key Scopes, Hashing & Revocation** | Automated (`test_integrations_and_incidents.py`, `test_workspaces_and_isolation.py`) | `fs_live_` SHA-256 hashed at rest, plaintext shown once; revoked/invalid/wrong-scope/cross-tenant keys return `401` | Verified `200` valid, `401` invalid & revoked, `key_hash` omitted | **PASS** |
| **JWT Validation (Exp, Aud, Iss)** | Automated (`test_security_foundation.py`) | Reject expired, wrong `aud`, wrong `iss`, and invalid signatures; forbid `local_dev` in `production` | All rejected with `AuthenticationError` / `ValidationError` | **PASS** |
| **Live Supabase Cloud Auth** | External service unavailable (`SUPABASE_URL` unset) | Validated against live Supabase JWKS | **BLOCKED** (only mocked RSA RS256 JWKS verified) | **BLOCKED** |
| **Multi-Tenant & RBAC Isolation** | Automated (`test_workspaces_and_isolation.py`) + live E2E (`phase8_live_e2e.py`) | Non-members get `403`; viewers cannot mutate (`403`); client `PATCH` cannot escalate `plan` | All `403` / plan locked to `free` | **PASS** |
| **Rate Limiting** | Live Redis 7 `rl:*` key creation (Phase 7) + `RateLimiter` enforcement check (`test_phase11_security_and_monitors.py`) | Enforces window & raises `RateLimitExceeded` (`429`) when exceeded | Verified live Redis key + `RateLimitExceeded` on 3rd request | **PASS** |
| **Payload Sanitization & Secret Leakage** | Automated (`test_normalization_and_detection.py`) + live n8n container log check (`phase11_real_n8n.py`) | Redacts auth headers, `token=`, `sk_live_`, JWTs; `GeminiProvider` uses `x-goog-api-key` header; no n8n key in logs or API JSON | All secrets redacted; `NO_N8N_API_KEY_IN_BACKEND_LOGS` | **PASS** |

---

## 2. Security Findings & Remediations Applied (Phases 6–11)

1. **HIGH — IPv4-Mapped IPv6 & DNS Rebinding SSRF Gap (Fixed Phase 6):** Unwrapped `ipv4_mapped`/`sixtofour` in `backend/app/core/ssrf.py` and added `_SSRFSafeSyncBackend` (`build_ssrf_safe_transport(trust_env=False)`).
2. **HIGH — Missing Supabase JWT `issuer` Enforcement (Fixed Phase 6):** Added `issuer=f"{SUPABASE_URL}/auth/v1"` validation in `backend/app/core/security.py`.
3. **MEDIUM — Inline Credential Leakage & Gemini Query-String Key (Fixed Phase 8):** Extended `SENSITIVE_VALUE_PATTERNS` in `backend/app/integrations/normalizer.py` (`token=`, `api_key=`, `sk_live_`, `fs_live_`) and moved Gemini key to `"x-goog-api-key"` header in `backend/app/intelligence/providers.py`.
4. **MEDIUM — Unbounded Webhook Body & Unused API Key Auth (Fixed Phase 6):** Added 1 MB body cap (`413`) in `backend/app/api/v1/ingest.py` and scoped `X-API-Key` verification in `backend/app/api/deps.py`.

---

## 3. Remaining Security Blockers Before Public Production

1. **Live Supabase Cloud Auth Verification:** Must run end-to-end token issuance, refresh, password reset, and RS256 JWKS rotation checks against an actual Supabase project.
2. **Trusted Proxy Edge Configuration:** `_extract_client_ip` relies on `X-Real-IP` / `X-Forwarded-For`; production TLS reverse proxy (Caddy/Nginx/Cloudflare) must strip/overwrite client-supplied forwarding headers.
3. **Production Secret & Dependency Scanning in CI:** Automate `pip-audit` and `npm audit` on every PR prior to image promotion.
