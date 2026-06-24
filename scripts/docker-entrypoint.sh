#!/bin/sh
set -e

if [ "${RUN_DB_MIGRATIONS:-true}" = "true" ]; then
  echo "Running database migrations..."
  alembic upgrade head
fi

exec "$@"
