#!/bin/sh
# release_check.sh — gate local para validar release antes de abrir PR.

set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[1/6] Backend tests"
cd "$ROOT_DIR"
.venv/bin/python -m pytest -q tests/test_api.py tests/test_spiders.py

echo "[2/6] Frontend tests"
cd "$ROOT_DIR/frontend"
npm run test

echo "[3/6] Frontend typecheck"
npx tsc --noEmit

echo "[4/6] Frontend build"
npm run build

echo "[5/6] Python syntax check (changed core files)"
cd "$ROOT_DIR"
.venv/bin/python -m py_compile \
  api/main.py \
  api/middleware.py \
  api/routers/scrape.py \
  api/routers/jobs.py \
  api/routers/data.py \
  api/routers/auth.py \
  worker/celery_config.py \
  worker/tasks.py \
  worker/logging_config.py

echo "[6/6] Alembic offline SQL generation"
cd "$ROOT_DIR/database"
../.venv/bin/alembic -c alembic.ini upgrade head --sql > /tmp/webscraper_migration_head.sql

echo "Release check OK"
