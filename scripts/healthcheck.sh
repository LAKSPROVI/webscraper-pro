#!/bin/sh
# healthcheck.sh — verificação rápida de serviços da stack.

set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

check_service() {
  service="$1"
  if docker compose -f "$ROOT_DIR/docker-compose.yml" ps "$service" 2>/dev/null | grep -q "Up"; then
    echo "[OK] $service"
  else
    echo "[ERRO] $service"
  fi
}

echo "== Status de serviços =="
check_service postgres
check_service redis
check_service scraper-api
check_service scraper-worker
check_service scraper-beat

echo "== Endpoints =="
if wget -qO- http://localhost:8000/health >/dev/null 2>&1; then
  echo "[OK] API /health"
else
  echo "[ERRO] API /health"
fi

if wget -qO- http://localhost:9090/-/healthy >/dev/null 2>&1; then
  echo "[OK] Prometheus"
else
  echo "[ERRO] Prometheus"
fi
