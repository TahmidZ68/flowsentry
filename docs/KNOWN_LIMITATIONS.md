# FlowSentry — Phase 11 Known Limitations & Blockers

**Last Updated:** 2026-11-23  
**Current Gate:** **READY FOR STAGING**

---

## 1. Blocked External Integrations (Unavailable Credentials / Infrastructure)

| Capability | Current Evidence | Why Blocked | Unblock Action |
|---|---|---|---|
| **Remote Staging / Production Deployment** | Local Docker Compose `--profile prod` verified (7 healthy containers) | No remote VPS, cloud host, DNS domain, or TLS certificate provisioned/authorized | Provision VPS/cloud host, point DNS, enable Caddy/Certbot TLS, deploy with `AUTH_MODE=supabase` |
| **Live Supabase Cloud Auth** | `local_dev` auth verified live; RS256 JWKS + issuer verification tested with mocked RSA keypair | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` unset | Create Supabase project, set env vars, run live signup/login/password-reset verification |
| **External Production SMTP Relay** | Real SMTP protocol verified via local `axllent/mailpit` container | `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD` for SES/SendGrid/Postmark unset | Provision transactional email provider + SPF/DKIM/DMARC, test `Send Test Email` |
| **Live Slack Incoming Webhook** | Masked config, SSRF guard, suppression, and retry verified with `MockTransport` | `SLACK_WEBHOOK_URL` unset | Connect test Slack workspace incoming webhook and verify alert + recovery messages |
| **Live OpenAI & Gemini APIs** | HTTP header hygiene, timeout/429/invalid JSON retry, token accounting, and fallback verified with `MockTransport`; deterministic fallback verified live | `OPENAI_API_KEY` & `GEMINI_API_KEY` unset | Configure API keys in staging and execute live investigation verification |
| **Remote Cloud n8n Instance** | Real `n8nio/n8n` v2.48.7 container verified end-to-end (15 steps) over Docker network with temporary `ALLOW_PRIVATE_INTEGRATION_HOSTS=true` | No external customer/cloud n8n instance URL/API key provided | Connect an external HTTPS n8n Cloud / self-hosted instance from staging |
| **Self-Serve Stripe Billing** | `BillingProvider` protocol + `NoopBillingProvider` stub; server-side plan quotas enforced | Stripe account & checkout integration deferred by design | Implement `StripeBillingProvider` when commercial billing is authorized |

---

## 2. Architectural & Product Limitations

1. **Docker Network / Private Self-Hosted n8n Requires Explicit Opt-In:** `ALLOW_PRIVATE_INTEGRATION_HOSTS` defaults to `false` to prevent SSRF against VPC/metadata targets. Agencies connecting a self-hosted n8n on a private network must either use **Webhook-Only** mode (recommended — n8n pushes outbound to FlowSentry) or deploy FlowSentry inside their private VPC with `ALLOW_PRIVATE_INTEGRATION_HOSTS=true`.
2. **React 18 Deprecation Warning in Next.js 16:** `next build` passes cleanly with React `18.3.1`, emitting Next.js 16's notice that React 18 support will be removed in Next.js 17. Upgrading to React 19 should be scheduled prior to Next.js 17.
3. **Sync Endpoint Performs Blocking Outbound I/O:** Manual `POST /integrations/{id}/sync` and `POST /outcome-monitors/{id}/check` run synchronously in the request worker (`httpx` timeouts capped at 5s–10s), while scheduled polling/checks run asynchronously in Celery. Large n8n histories (many pages) should prefer Celery sync (`flowsentry.sync_integration`).
4. **Software License:** No `LICENSE` file is published yet pending explicit authorization from the project owner.
5. **Local Host Docker Daemon State at Session End:** Docker Desktop was not running after the host restart prior to final doc generation; container runtime checks cited in `REAL_WORLD_VALIDATION.md` were observed prior to that restart, while all 40 backend tests, `ruff`, `tsc`, 10 Vitest tests, `eslint`, `next build`, and `npm audit` ran and passed cleanly on the final codebase.
