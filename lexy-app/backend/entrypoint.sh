#!/bin/sh
set -e

echo "Waiting for Postgres at $DB_HOST:$DB_PORT..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -q; do
  sleep 1
done
echo "Postgres is ready."

echo "Running database migrations..."
cd /app/backend
alembic upgrade head

echo "Starting server..."
cd /app
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
