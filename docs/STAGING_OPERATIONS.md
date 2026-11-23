# FlowSentry — Staging Operations Runbook

Routine day-2 operations for a single-server remote staging deployment using [`docker-compose.yml`](../docker-compose.yml) + [`docker-compose.staging.yml`](../docker-compose.staging.yml).

---

## 1. Service & Health Inspection

```bash
# Service health summary
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod ps

# Tail logs without leaking encrypted DB secrets (JsonFormatter redacts auth/API keys)
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod logs -f --tail=100 backend worker beat

# API & dependency health checks
curl -fsS https://staging.flowsentry.example/health
curl -fsS https://staging.flowsentry.example/ready
```

---

## 2. TLS Certificate Renewal (Let's Encrypt)

Because Nginx serves `/.well-known/acme-challenge/` from `./infrastructure/nginx/certbot` (`webroot`), certificates renew cleanly **without stopping Nginx**:

```bash
sudo certbot renew --webroot -w "$(pwd)/infrastructure/nginx/certbot" --quiet
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod exec nginx nginx -s reload
```

Schedule via root crontab or systemd timer (`certbot.timer`) with a `--deploy-hook` reloading the `flowsentry-nginx` container.

---

## 3. Database Migration & Backup Procedure

> [!IMPORTANT]
> Always take and verify a PostgreSQL backup **before** applying schema migrations or pulling new images. Never run destructive SQL against a populated environment without an offsite backup.

```bash
# 1. Create compressed PostgreSQL dump
./scripts/backup_db.sh

# 2. Verify backup restores cleanly into an isolated verification DB (non-destructive)
LATEST_BACKUP=$(ls -t ./backups/flowsentry_*.sql.gz | head -n1)
./scripts/restore_db.sh "$LATEST_BACKUP" flowsentry_restore_verify

# 3. Verify Alembic head and connectivity
docker compose -f docker-compose.yml -f docker-compose.staging.yml exec backend alembic current
docker compose -f docker-compose.yml -f docker-compose.staging.yml exec postgres \
  psql -U flowsentry -d flowsentry -c "\dt"
```

---

## 4. Optional External Providers Visibility & Behavior

- **OpenAI / Gemini unconfigured (`OPENAI_API_KEY` & `GEMINI_API_KEY` empty):** Application starts cleanly; incidents investigate via `DeterministicFallbackAnalyzer` (`provider="deterministic"`, `model="rule-engine-v1"`).
- **SMTP unconfigured (`SMTP_HOST` empty):** Application starts cleanly; Slack notifications continue working, while email deliveries log failed status in `notifications` table (`SMTP_HOST is not configured`) without crashing workers.
- **Slack unconfigured:** Application starts cleanly; workspace preferences remain disabled until configured in `/notifications`.
- **Supabase Auth:** Required when `AUTH_MODE=supabase` (`ENVIRONMENT=production` refuses startup without `SUPABASE_URL` or `SUPABASE_JWT_SECRET`).

---

## 5. Log Rotation, Volumes & Cleanup

- Container logs rotate automatically (`json-file`, `max-size: 10m`, `max-file: 5`).
- Persistent named volumes: `postgres_data` (database) and `redis_data` (Redis AOF `--appendonly yes`).
- Retention cleanup runs every `86400s` via Celery Beat (`flowsentry.cleanup_expired_records`), pruning `executions` and `outcome_monitor_runs` older than each workspace plan's `retention_days`.
