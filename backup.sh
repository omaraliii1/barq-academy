#!/usr/bin/env bash
# Back up the BARQ PostgreSQL database.
#
# Usage:
#   ./backup.sh [--project NAME] [--output FILE]
#
# Takes a pg_dump (custom format, -F c) of the running postgres container
# and writes it to backups/. Custom format is required so restore.sh can
# use pg_restore --clean --if-exists for a clean, repeatable restore.
set -euo pipefail

PROJECT="barq-assessment"
OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    --output)  OUTPUT="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

# Load DB name/user from .env if present, falling back to the known defaults.
POSTGRES_USER="barq_app"
POSTGRES_DB="barq_tasks"
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

BACKUP_DIR="backups"
mkdir -p "$BACKUP_DIR"

if [[ -z "$OUTPUT" ]]; then
  TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  OUTPUT="${BACKUP_DIR}/barq_tasks_${TIMESTAMP}.dump"
fi

echo "== BARQ PostgreSQL backup =="
echo "Project:    $PROJECT"
echo "Database:   $POSTGRES_DB (user: $POSTGRES_USER)"
echo "Output:     $OUTPUT"

# Confirm the postgres container is up and healthy before attempting a dump.
STATUS="$(docker compose -p "$PROJECT" ps postgres --format '{{.Health}}' 2>/dev/null || true)"
if [[ "$STATUS" != "healthy" ]]; then
  echo "[FAIL] postgres container is not healthy (status: '${STATUS:-not running}')." >&2
  echo "        Start the environment first: docker compose -p $PROJECT up -d" >&2
  exit 1
fi

# pg_dump in custom format (-F c): compressed, and restorable with pg_restore.
if docker compose -p "$PROJECT" exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c > "$OUTPUT"; then
  SIZE="$(du -h "$OUTPUT" | cut -f1)"
  echo "[PASS] Backup written: $OUTPUT ($SIZE)"
  exit 0
else
  echo "[FAIL] pg_dump failed." >&2
  rm -f "$OUTPUT"
  exit 1
fi
