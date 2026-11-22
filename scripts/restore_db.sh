#!/usr/bin/env bash
set -euo pipefail

# PostgreSQL restore helper for Docker Compose deployments.
# Defaults to restoring into a separate verification database (flowsentry_restore_verify)
# unless TARGET_DB is explicitly specified.
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <backup.sql.gz> [target_db]" >&2
  exit 1
fi

BACKUP_FILE="$1"
TARGET_DB="${2:-flowsentry_restore_verify}"
POSTGRES_USER="${POSTGRES_USER:-flowsentry}"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$TARGET_DB\";" \
  -c "CREATE DATABASE \"$TARGET_DB\" OWNER \"$POSTGRES_USER\";"

gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$TARGET_DB" -v ON_ERROR_STOP=1 >/dev/null

echo "Restore completed into database '$TARGET_DB' from '$BACKUP_FILE'"
