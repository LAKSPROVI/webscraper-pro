#!/bin/sh
# stage_commit_batch.sh — organiza as mudanças em lotes lógicos de commit.
# Uso:
#   sh scripts/stage_commit_batch.sh show
#   sh scripts/stage_commit_batch.sh api-security
#   sh scripts/stage_commit_batch.sh frontend-qa
#   sh scripts/stage_commit_batch.sh infra-ops
#
# O script apenas faz git add dos arquivos do lote escolhido.
# Ele não executa git commit automaticamente.

set -eu

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

show_batch() {
  batch="$1"
  case "$batch" in
    api-security)
      cat <<'EOF'
Commit sugerido: feat(api): harden backend security and auth

Arquivos:
  .env.example
  api/main.py
  api/middleware.py
  api/models/celery_app.py
  api/requirements.txt
  api/rate_limiter.py
  api/routers/auth.py
  api/routers/data.py
  api/routers/jobs.py
  api/routers/scrape.py
EOF
      ;;
    frontend-qa)
      cat <<'EOF'
Commit sugerido: feat(frontend): add resilience and QA tooling

Arquivos:
  frontend/.storybook/main.ts
  frontend/.storybook/preview.ts
  frontend/eslint.config.js
  frontend/package-lock.json
  frontend/package.json
  frontend/src/components/ui/ErrorBoundary.test.tsx
  frontend/src/components/ui/ErrorBoundary.tsx
  frontend/src/components/ui/NeonButton.stories.tsx
  frontend/src/main.tsx
  frontend/src/pages/Spiders.tsx
  frontend/src/test/setup.ts
  frontend/vite.config.ts
EOF
      ;;
    infra-ops)
      cat <<'EOF'
Commit sugerido: chore(infra): prepare release workflow and runtime ops

Arquivos:
  .devcontainer/devcontainer.json
  .github/workflows/ci.yml
  .gitignore
  Makefile
  README.md
  api/routers/schedule.py
  api/routers/spiders.py
  database/migrations/versions/002_performance_indexes.py
  docker-compose.yml
  k8s/api-deployment.yaml
  k8s/worker-deployment.yaml
  scripts/healthcheck.sh
  scripts/release_check.sh
  tests/test_spiders.py
  worker/Dockerfile
  worker/celery_config.py
  worker/logging_config.py
  worker/tasks.py
EOF
      ;;
    *)
      echo "Lote desconhecido: $batch" >&2
      exit 1
      ;;
  esac
}

stage_batch() {
  batch="$1"
  case "$batch" in
    api-security)
      git add \
        .env.example \
        api/main.py \
        api/middleware.py \
        api/models/celery_app.py \
        api/requirements.txt \
        api/rate_limiter.py \
        api/routers/auth.py \
        api/routers/data.py \
        api/routers/jobs.py \
        api/routers/scrape.py
      ;;
    frontend-qa)
      git add \
        frontend/.storybook/main.ts \
        frontend/.storybook/preview.ts \
        frontend/eslint.config.js \
        frontend/package-lock.json \
        frontend/package.json \
        frontend/src/components/ui/ErrorBoundary.test.tsx \
        frontend/src/components/ui/ErrorBoundary.tsx \
        frontend/src/components/ui/NeonButton.stories.tsx \
        frontend/src/main.tsx \
        frontend/src/pages/Spiders.tsx \
        frontend/src/test/setup.ts \
        frontend/vite.config.ts
      ;;
    infra-ops)
      git add \
        .devcontainer/devcontainer.json \
        .github/workflows/ci.yml \
        .gitignore \
        Makefile \
        README.md \
        api/routers/schedule.py \
        api/routers/spiders.py \
        database/migrations/versions/002_performance_indexes.py \
        docker-compose.yml \
        k8s/api-deployment.yaml \
        k8s/worker-deployment.yaml \
        scripts/healthcheck.sh \
        scripts/release_check.sh \
        tests/test_spiders.py \
        worker/Dockerfile \
        worker/celery_config.py \
        worker/logging_config.py \
        worker/tasks.py
      ;;
    *)
      echo "Lote desconhecido: $batch" >&2
      exit 1
      ;;
  esac

  echo "Lote stageado: $batch"
  echo
  git diff --cached --stat
}

case "${1:-show}" in
  show)
    show_batch api-security
    echo
    show_batch frontend-qa
    echo
    show_batch infra-ops
    ;;
  api-security|frontend-qa|infra-ops)
    stage_batch "$1"
    ;;
  *)
    echo "Uso: sh scripts/stage_commit_batch.sh [show|api-security|frontend-qa|infra-ops]" >&2
    exit 1
    ;;
esac
