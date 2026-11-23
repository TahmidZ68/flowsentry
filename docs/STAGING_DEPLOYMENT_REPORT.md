# FlowSentry — Phase 13 Remote Staging Deployment Report

**Report Date:** 2026-11-23  
**Git Branch / Baseline Commit:** `main` (`9f02dc3` + Phase 13 staging deployment hardening)  
**Target Environment:** Single-Server Remote Staging (Not Yet Provisioned)  
**Gate Decision:** **READY FOR STAGING DEPLOYMENT** *(Remote deployment **BLOCKED** pending host provisioning, domain/DNS, external service credentials, and explicit authorization)*

---

## 1. Honest Execution & Authorization Status

Per Section 11 (*Authorization Boundaries*):
- No remote VPS or cloud server was purchased or provisioned.
- No domain was registered or DNS modified.
- No external paid SaaS accounts (Supabase Cloud, OpenAI, Gemini, Slack, transactional SMTP) were created or queried.
- Therefore, live remote deployment has **not** occurred (`STAGING DEPLOYED AND VERIFIED` is **not** claimed). All repository, security, Compose, TLS, migration, and operational preparations achievable locally have been completed and verified.

---

## 2. Single-Server VPS Infrastructure Plan

FlowSentry runs cleanly on a single Docker host using [`docker-compose.yml`](../docker-compose.yml) + [`docker-compose.staging.yml`](../docker-compose.staging.yml) with `--profile prod` (7 containers: `postgres`, `redis`, `backend`, `worker`, `beat`, `frontend`, `nginx`), avoiding Kubernetes or distributed orchestrator complexity.

### Resource Sizing & Cost Estimate

| Dimension | Minimum Recommended Staging Spec | Technical Rationale (Observed Code & Caps) |
|---|---|---|
| **CPU** | **2 vCPU** (shared or dedicated x86_64/ARM64) | Supports concurrent Nginx TLS termination, FastAPI (`uvicorn`), Next.js standalone server, Celery worker (`--concurrency=2`), Celery Beat, PostgreSQL 16, and in-place `docker compose build` (`next build` + `tsc`). |
| **RAM** | **4 GB RAM** (+ `2 GB` host swap file) | Sum of explicit container `mem_limit` caps in `docker-compose.staging.yml` is **`3,200 MiB`** (`postgres: 768m`, `redis: 256m`, `backend: 768m`, `worker: 512m`, `beat: 256m`, `frontend: 512m`, `nginx: 128m`), leaving ~800 MiB for Linux OS + Docker Engine and avoiding OOM kills during `next build`. |
| **Storage** | **40–60 GB NVMe SSD** | Docker base images + build cache (~6–10 GB), PostgreSQL `postgres_data` + Redis AOF `redis_data` (~5–15 GB staging growth with daily retention pruning), rotating container logs (`10m × 5` per container = max 350 MB), and local staging `pg_dump` backups. |
| **Operating System** | **Ubuntu 24.04 LTS** (minimal server image) | Long-term kernel/Docker Engine support, native `ufw`, `unattended-upgrades`, and Certbot/Docker Compose v2 compatibility. |
| **Estimated Monthly Cost** | **~$12–$24 / month** (VPS) + **~$10–$15 / year** (domain) | Single 2 vCPU / 4 GB NVMe VPS (e.g., Hetzner CX22 / DigitalOcean Basic / Linode Shared) + object storage bucket (~$0–$5/mo for encrypted offsite `pg_dump` backups). *Assumes moderate staging/beta traffic and Supabase Free/Pro tier + optional LLM token usage.* |

### Host Firewall & Network Isolation
- **Public Ports Allowed (UFW):** `22/tcp` (restricted to operator IP / SSH key auth only), `80/tcp` (ACME HTTP-01 challenge + 301 HTTPS redirect), and `443/tcp` (Nginx HTTPS).
- **Internal Ports Blocked / Unbound:**
  - Base `docker-compose.yml` binds `postgres` (`5432`), `redis` (`6379`), `backend` (`8000`), and `frontend` (`3000`) strictly to `127.0.0.1` instead of `0.0.0.0`.
  - Staging override `docker-compose.staging.yml` clears host port bindings (`ports: !reset []`) for `postgres`, `redis`, `backend`, and `frontend` so Docker `iptables` never exposes internal containers directly, enforcing all external traffic through Nginx (`80`/`443`).

### Backup Storage Strategy
- Automated local compressed `pg_dump` via [`scripts/backup_db.sh`](../scripts/backup_db.sh) (retention: 14–30 days on host `./backups/`).
- Copy encrypted daily archives off-server (e.g., S3-compatible bucket / Backblaze B2 / Cloudflare R2 via `rclone` or `aws s3 cp` with server-side or client-side GPG/age encryption) so single-VPS disk loss does not destroy database state.

---

## 3. Phase 13 Configuration Hardening Verified Locally

1. **Docker Port & Redis Hardening (`docker-compose.yml` + `docker-compose.staging.yml`):**
   - Eliminated `0.0.0.0` default port exposure on `postgres`, `redis`, `backend`, and `frontend`.
   - Added staging Redis password enforcement (`--requirepass` + `REDISCLI_AUTH` healthcheck + matching `REDIS_URL`/`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` template in [`.env.production.example`](../.env.production.example)).
   - Added `--concurrency=2` on Celery worker and explicit `mem_limit` caps across all 7 staging containers.
   - Added `/etc/letsencrypt` and `./infrastructure/nginx/certbot` read-only volume mounts plus `80:80` and `443:443` bindings on `nginx` in `docker-compose.staging.yml`.
2. **Nginx TLS Syntax Update ([`infrastructure/nginx/nginx.tls.conf.example`](../infrastructure/nginx/nginx.tls.conf.example)):**
   - Updated `listen 443 ssl http2;` to `listen 443 ssl;` + `http2 on;` for `nginx:1.27-alpine` compatibility.
3. **Database Schema & Migrations Verified (`backend/migrations/versions/56bf9a530d98_initial_schema.py`):**
   - Confirmed Alembic initial migration covers all 19 tables, foreign-key cascade rules, unique constraints (`uq_execution_wf_ext_id`, `uq_workspace_member`, `uq_notif_pref_ws_channel`, `key_hash`, etc.), composite indexes, and clean `downgrade()`.

---

## 4. Required Operator Inputs & Exact Remote Deployment Commands

### Required Inputs Before Executing Remote Deployment
1. **Provisioned VPS:** Public IPv4/IPv6, SSH access (`ubuntu` / root key), and permission to deploy.
2. **Domain & DNS:** Staging domain/subdomain (e.g., `staging.flowsentry.example`) with `A` (and `AAAA`) record pointing to VPS IP.
3. **Supabase Cloud Project:** `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, plus Staging Site URL & Redirect URLs configured.
4. **Optional Integrations (non-blocking at startup):**
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`
   - `OPENAI_API_KEY` and/or `GEMINI_API_KEY`
   - Slack Incoming Webhook URL + Remote HTTPS `n8n` URL/API key (configured in UI after sign-in).

### Exact Staging Provision & Deploy Sequence (Run on Ubuntu 24.04 VPS After Authorization)

```bash
# 1. Host firewall & Docker installation (run as sudo)
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# 2. Clone repo and generate cryptographic keys
git clone <YOUR_REPO_URL> flowsentry
cd flowsentry
python3 scripts/generate_keys.py

# 3. Prepare environment and TLS Nginx config (never commit .env or nginx.tls.conf)
cp .env.production.example .env
# Edit .env: set ENVIRONMENT=staging, ALLOWED_ORIGINS=https://staging.flowsentry.example,
# strong POSTGRES_PASSWORD & REDIS_PASSWORD, ENCRYPTION_KEY, SUPABASE_URL,
# NEXT_PUBLIC_API_URL=, NEXT_PUBLIC_AUTH_MODE=supabase, NEXT_PUBLIC_SUPABASE_URL/ANON_KEY

cp infrastructure/nginx/nginx.tls.conf.example infrastructure/nginx/nginx.tls.conf
sed -i 's/app\.flowsentry\.example/staging.flowsentry.example/g' infrastructure/nginx/nginx.tls.conf
mkdir -p infrastructure/nginx/certbot

# 4. Obtain real Let's Encrypt certificate before starting TLS Nginx
sudo apt-get update && sudo apt-get install -y certbot
sudo certbot certonly --standalone -d staging.flowsentry.example \
  --agree-tos -m ops@flowsentry.example --non-interactive

# 5. Build, run Alembic migrations cleanly on startup, and boot full staging stack
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod build --no-cache frontend backend
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod up -d
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod ps
```

---

## 5. Runtime State Tracking Fields (To Be Populated Upon Live Staging Run)

| Field | Current Value |
|---|---|
| **Host Configuration** | `UNPROVISIONED` (Target: Ubuntu 24.04 LTS, 2 vCPU, 4 GB RAM, 40–60 GB NVMe) |
| **Deployment Version** | `9f02dc3` + Phase 13 hardening (local Git `main`) |
| **Deployment Timestamp** | `NOT DEPLOYED YET` |
| **Container Health** | `NOT RUN ON REMOTE HOST` (`docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod config --quiet` passed locally) |
| **Database Status** | Alembic revision `56bf9a530d98` verified in repo; remote PostgreSQL not yet provisioned |
| **External Integration Status** | Supabase, OpenAI, Gemini, Slack, External SMTP, Remote HTTPS n8n: `BLOCKED / UNVERIFIED` |
| **Known Limitations** | See [`docs/KNOWN_LIMITATIONS.md`](./KNOWN_LIMITATIONS.md) |
