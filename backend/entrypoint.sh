#!/usr/bin/env sh
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
RUN_MIGRATIONS="${RUN_MIGRATIONS:-false}"

mkdir -p /app/data /app/logs

if [ "$RUN_MIGRATIONS" = "true" ]; then
  echo "Running migrations..."
  alembic upgrade head
fi

exec uvicorn app.main:app --host "$HOST" --port "$PORT"
