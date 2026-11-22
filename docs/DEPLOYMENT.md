# FlowSentry — Deployment & Operations Guide

## 1. Docker Compose (Local & Single-Host VPS)
1. Copy `.env.example` to `.env` and set production values:
   - `ENVIRONMENT=production`
   - `DEBUG=false`
   - `AUTH_MODE=supabase`
   - `SUPABASE_URL` & `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `ENCRYPTION_KEY` (generated via `python scripts/generate_keys.py`)
   - `ALLOWED_ORIGINS=https://app.yourdomain.com`
   - `NEXT_PUBLIC_API_URL=https://app.yourdomain.com`
2. Start the full stack with Nginx reverse proxy:
   ```bash
   docker compose --profile prod up -d --build
   ```
3. Verify health endpoints:
   - `GET http://localhost/health` -> `{"status":"ok","service":"flowsentry-api"}`
   - `GET http://localhost/ready` -> verifies PostgreSQL & Redis connectivity.

## 2. VPS Production Hardening (Ubuntu / Debian)
- Place TLS termination (e.g., Caddy, Certbot/Nginx SSL, or Cloudflare Proxy) in front of port `80` / `443`.
- Firewall ports `5432` (PostgreSQL) and `6379` (Redis) so they are never exposed publicly.
- Run behind a non-root user (already enforced in `backend.Dockerfile` and `frontend.Dockerfile`).
- Configure automated daily database backups.

## 3. Database Backup & Restore
### Backup
```bash
./scripts/backup_db.sh
```
Or manually:
```bash
docker compose exec -T postgres pg_dump -U flowsentry flowsentry | gzip > backup_$(date +%F).sql.gz
```

### Restore
```bash
gunzip -c backup_YYYY-MM-DD.sql.gz | docker compose exec -T postgres psql -U flowsentry flowsentry
```

### Alembic Migrations
`backend` automatically runs `alembic upgrade head` on container startup before launching `uvicorn`.
