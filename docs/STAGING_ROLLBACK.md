# FlowSentry — Staging Rollback & Recovery Procedure

Use this runbook if a staging deployment introduces regressions, failed migrations, container instability, or data corruption.

---

## 1. Pre-Deploy Safety Rule

Before every upgrade:
1. Record the currently healthy Git SHA (`git rev-parse HEAD > /tmp/flowsentry_prev_sha`).
2. Take a PostgreSQL backup via `./scripts/backup_db.sh` and note the filename.

---

## 2. Application Code Rollback (No Breaking Schema Change)

```bash
# 1. Check out the previously known-good commit
PREV_SHA=$(cat /tmp/flowsentry_prev_sha)
git checkout "$PREV_SHA"

# 2. Rebuild and restart services
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod build frontend backend
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod up -d

# 3. Verify health & readiness
curl -fsS https://staging.flowsentry.example/health
curl -fsS https://staging.flowsentry.example/ready
```

---

## 3. Database Migration Rollback

If an Alembic migration failed or must be reverted:

```bash
# Option A: Downgrade 1 Alembic revision cleanly (only if reversible and no data loss)
docker compose -f docker-compose.yml -f docker-compose.staging.yml exec backend alembic downgrade -1

# Option B: Full point-in-time restore from pre-deploy pg_dump archive
# Stop app/worker writers first so active connections close cleanly
docker compose -f docker-compose.yml -f docker-compose.staging.yml stop backend worker beat

# Restore into a verification database first to confirm backup integrity
./scripts/restore_db.sh ./backups/flowsentry_<TIMESTAMP>.sql.gz flowsentry_restore_verify

# After verifying flowsentry_restore_verify, replace target DB and restart services
./scripts/restore_db.sh ./backups/flowsentry_<TIMESTAMP>.sql.gz flowsentry
docker compose -f docker-compose.yml -f docker-compose.staging.yml --profile prod up -d
```

---

## 4. Persistent Volume & Configuration Recovery

- **Redis corruption/restart:** `redis_data` persists AOF state; if broker queue state must be cleared during an incident, stop `worker`/`beat`, run `FLUSHALL` inside Redis with `REDISCLI_AUTH`, and restart `worker`/`beat`.
- **`.env` or `ENCRYPTION_KEY` loss warning:** Keep an offline encrypted copy of `.env` (`ENCRYPTION_KEY`) in a team password manager/vault. Losing `ENCRYPTION_KEY` makes existing `integrations.encrypted_credentials` and `notification_preferences.encrypted_config` unreadable and requires users to re-enter integration/Slack secrets.
- **Nginx TLS config rollback:** Keep previous working `infrastructure/nginx/nginx.tls.conf.bak` on the host; restore and run `docker compose ... exec nginx nginx -t && nginx -s reload`.
