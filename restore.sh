#!/usr/bin/env bash
# Restore the BARQ PostgreSQL database from a backup made by backup.sh.
#
# Usage:
#   ./restore.sh [--project NAME] [FILE]
#
# FILE defaults to the most recent backups/*.dump. Uses pg_restore with
# --clean --if-exists so the restore is repeatable against a database
# that already has data (drops and recreates objects before loading).
# After restoring, verifies the "records" table is queryable and prints
# its row count as evidence the restore actually worked.
set -euo pipefail

PROJECT="barq-assessment"
FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT="$2"; shift 2 ;;
    *) FILE="$1"; shift ;;
  esac
done

POSTGRES_USER="barq_app"
POSTGRES_DB="barq_tasks"
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

if [[ -z "$FILE" ]]; then
  FILE="$(ls -t backups/*.dump 2>/dev/null | head -n1 || true)"
fi

if [[ -z "$FILE" || ! -f "$FILE" ]]; then
  echo "[FAIL] No backup file found. Pass one explicitly or run ./backup.sh first." >&2
  exit 1
fi

echo "== BARQ PostgreSQL restore =="
echo "Project:    $PROJECT"
echo "Database:   $POSTGRES_DB (user: $POSTGRES_USER)"
echo "Source:     $FILE"

STATUS="$(docker compose -p "$PROJECT" ps postgres --format '{{.Health}}' 2>/dev/null || true)"
if [[ "$STATUS" != "healthy" ]]; then
  echo "[FAIL] postgres container is not healthy (status: '${STATUS:-not running}')." >&2
  echo "        Start the environment first: docker compose -p $PROJECT up -d" >&2
  exit 1
fi

if ! docker compose -p "$PROJECT" exec -T postgres \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < "$FILE"; then
  echo "[FAIL] pg_restore reported an error." >&2
  exit 1
fi

echo "[PASS] pg_restore completed."

# Prove recovery: query the records table and show the row count.
COUNT="$(docker compose -p "$PROJECT" exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM records;" | tr -d '[:space:]')"

if [[ "$COUNT" =~ ^[0-9]+$ ]]; then
  echo "[PASS] records table is queryable after restore: $COUNT row(s)."
  exit 0
else
  echo "[FAIL] Could not verify records table after restore." >&2
  exit 1
fi
