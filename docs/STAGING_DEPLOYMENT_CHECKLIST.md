# FlowSentry — Staging Deployment Checklist

Follow this exact sequence to deploy FlowSentry to a clean remote staging environment (Ubuntu LTS / Docker Compose host) and advance validation from **READY FOR STAGING** to **READY FOR CONTROLLED BETA**.

---

## 1. Pre-Deployment Host Preparation

- [ ] Provision Linux VM/instance with Docker Engine + Docker Compose v2 plugin and outbound HTTPS access (`443`, `587`/`465` for SMTP).
- [ ] Point DNS `A`/`AAAA` record (e.g., `staging.flowsentry.example`) to the host public IP.
- [ ] Configure host/cloud firewall so **only `22` (restricted), `80`, and `443`** are publicly reachable; keep `5432`, `6379`, `8000`, and `3000` private/localhost-only.
- [ ] Clone the repository at the verified `main` commit.

## 2. External Service & Environment Setup

- [ ] Follow [`docs/EXTERNAL_SERVICE_SETUP.md`](./EXTERNAL_SERVICE_SETUP.md) to configure:
  - [ ] Live **Supabase Cloud** project (`SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, Site URL & Redirect URLs).
  - [ ] External **SMTP relay** credentials (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`).
  - [ ] Optional **OpenAI** or **Google Gemini** API key (or leave unset for deterministic fallback).
  - [ ] Target **Slack workspace** Incoming Webhook URL (configured after login in `/notifications`).
  - [ ] Remote **HTTPS n8n instance** + n8n API key for end-to-end staging validation.
- [ ] Generate cryptographic keys (`python3 scripts/generate_keys.py`): copy Fernet `ENCRYPTION_KEY`.
- [ ] Copy `.env.production.example` to `.env` on the server (set `ENVIRONMENT=staging` for initial staging smoke tests, or `ENVIRONMENT=production` to enforce strict fail-closed guards), and fill in real values:
  - [ ] `AUTH_MODE=supabase`, `NEXT_PUBLIC_AUTH_MODE=supabase`
  - [ ] `DEBUG=false`
  - [ ] `ALLOWED_ORIGINS=https://staging.flowsentry.example`
  - [ ] `NEXT_PUBLIC_API_URL=` (blank for same-origin Nginx)
  - [ ] Strong `POSTGRES_PASSWORD` in both `POSTGRES_PASSWORD` and `DATABASE_URL`
  - [ ] `LOCAL_DEV_JWT_SECRET=` (blank)

## 3. TLS & Reverse Proxy Setup

- [ ] Copy `infrastructure/nginx/nginx.tls.conf.example` -> `infrastructure/nginx/nginx.conf` (or keep host Caddy/Nginx/ALB terminating TLS in front of port 80).
- [ ] Replace `app.flowsentry.example` with your real domain name and provision Let's Encrypt certificates via Certbot (`fullchain.pem`, `privkey.pem`), mounting `/etc/letsencrypt` into the `nginx` service.

## 4. Build, Migrate & Boot

```bash
docker compose --profile prod build --no-cache frontend backend
docker compose --profile prod up -d
docker compose --profile prod ps
```

- [ ] Verify all containers (`postgres`, `redis`, `backend`, `worker`, `beat`, `frontend`, `nginx`) report `healthy` / `running`.
- [ ] Inspect logs for startup errors or migration failures:
  ```bash
  docker compose --profile prod logs --tail=100 backend worker beat frontend nginx
  ```
- [ ] Confirm health & readiness endpoints:
  - [ ] `curl -fsS https://staging.flowsentry.example/health` returns `{"status":"ok","service":"flowsentry-api"}`.
  - [ ] `curl -fsS https://staging.flowsentry.example/ready` returns HTTP `200` with `database: "ok"` and `redis: "ok"`.
- [ ] When `ENVIRONMENT=production`, verify `/docs`, `/openapi.json`, and `POST /api/v1/auth/dev-token` all return `404`.

## 5. Live External Integration Smoke Tests (Required to Unlock Controlled Beta)

1. **Supabase Auth E2E:**
   - [ ] Sign up and confirm email via `/register` on `https://staging.flowsentry.example`.
   - [ ] Sign in via `/login`, create a workspace and project, refresh page, and confirm `/api/v1/auth/me` succeeds with Supabase JWKS JWT.
2. **Remote HTTPS n8n E2E:**
   - [ ] In `/integrations`, connect a remote `https://` n8n instance (`ALLOW_PRIVATE_INTEGRATION_HOSTS=false`), click **Validate**, and click **Sync**.
   - [ ] Configure the one-time `X-FlowSentry-Webhook-Secret` in an n8n Error Trigger workflow pointing to `https://staging.flowsentry.example/api/v1/ingest/webhooks/n8n/<id>`.
   - [ ] Execute an intentionally failing n8n workflow and confirm webhook receipt, incident creation, and dashboard visibility.
   - [ ] Fix the n8n workflow, execute `3` healthy runs (matching `recovery_consecutive_successes`), and confirm automatic incident resolution.
3. **Outcome Monitor & Notification E2E:**
   - [ ] Configure real Slack webhook and real external email recipients in `/notifications`.
   - [ ] Click **Send Test** on both channels and confirm delivery in Slack and external inbox (plus `sent` rows in Delivery Ledger).
   - [ ] Confirm duplicate suppression prevents alert flooding on repeated incident events, and `incident_resolved` fires upon recovery.
4. **Optional Live AI Check:**
   - [ ] Trigger an investigation on an incident (`/incidents/<id>`) and verify provider attribution, sanitized evidence separation, structured actions, and token recording (`UsageRecord` / `AIInvestigation`).
5. **Backup & Restore Drill:**
   - [ ] Run `./scripts/backup_db.sh` and restore into scratch verification DB via `./scripts/restore_db.sh ./backups/<file>.sql.gz` without errors.

## 6. Post-Smoke Sign-Off

- [ ] Update [`docs/PRODUCTION_STATUS.md`](./PRODUCTION_STATUS.md) recording staging verification dates, domain, and cleared blockers before inviting controlled beta customers.
