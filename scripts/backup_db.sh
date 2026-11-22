#!/usr/bin/env bash
set -euo pipefail

# PostgreSQL backup script for Docker Compose deployments
BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
POSTGRES_USER="${POSTGRES_USER:-flowsentry}"
POSTGRES_DB="${POSTGRES_DB:-flowsentry}"

mkdir -p "$BACKUP_DIR"
OUT_FILE="${BACKUP_DIR}/flowsentry_${TIMESTAMP}.sql.gz"

docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUT_FILE"
echo "Backup written to $OUT_FILE"
