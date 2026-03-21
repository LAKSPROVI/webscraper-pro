#!/bin/bash
# ==============================================================================
# entrypoint.sh — Script de inicialização do Worker Celery / Beat Scheduler
#
# Responsabilidades:
#   1. Aguardar Redis e PostgreSQL ficarem disponíveis
#   2. Executar migrações Alembic (apenas se ROLE=worker ou ROLE=beat)
#   3. Inicializar Playwright browsers (se necessário)
#   4. Iniciar o serviço conforme a variável ROLE:
#      - worker: Celery worker com filas configuradas
#      - beat:   Celery beat scheduler
#      - flower: Painel de monitoramento Flower
#      - all:    Worker + Beat na mesma instância (desenvolvimento)
# ==============================================================================

set -euo pipefail

# ── Cores para output legível ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Sem cor

log_info()    { echo -e "${GREEN}[INFO]${NC}  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_section() { echo -e "${BLUE}[====]${NC}  $(date '+%Y-%m-%d %H:%M:%S') ═══ $* ═══"; }

# ── Variáveis de configuração ──────────────────────────────────────────────
ROLE="${ROLE:-worker}"
CELERY_APP="${CELERY_APP:-worker.celery_config}"
CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-4}"
CELERY_QUEUES="${CELERY_QUEUES:-scraping,default}"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-info}"
CELERY_WORKER_HOSTNAME="${CELERY_WORKER_HOSTNAME:-worker@%h}"

REDIS_URL="${CELERY_BROKER_URL:-redis://redis:6379/0}"
DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://scraper:scraper_pass@postgres:5432/webscraper}"

# Extrai host e porta do Redis para o health check
REDIS_HOST=$(echo "$REDIS_URL" | sed -E 's|redis://([^:@/]+).*|\1|; s|redis://[^@]+@([^:]+).*|\1|')
REDIS_PORT=$(echo "$REDIS_URL" | sed -E 's|.*:([0-9]+).*|\1|; s|.*redis://[^:]+$|6379|' | head -1)
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

# Extrai host e porta do PostgreSQL
PG_HOST=$(echo "$DATABASE_URL" | sed -E 's|.*@([^:]+):.*|\1|')
PG_PORT=$(echo "$DATABASE_URL" | sed -E 's|.*:([0-9]+)/.*|\1|')
PG_HOST="${PG_HOST:-postgres}"
PG_PORT="${PG_PORT:-5432}"

MAX_WAIT="${MAX_WAIT_SECONDS:-60}"
WAIT_INTERVAL=2

# ── Tratamento de sinais para graceful shutdown ────────────────────────────
shutdown() {
    log_warn "Recebendo sinal de shutdown (SIGTERM/SIGINT)..."
    if [ -n "${CELERY_PID:-}" ]; then
        log_info "Enviando SIGTERM para processo Celery PID=$CELERY_PID"
        kill -TERM "$CELERY_PID" 2>/dev/null || true
        wait "$CELERY_PID" 2>/dev/null || true
    fi
    log_info "Worker encerrado com sucesso."
    exit 0
}

trap 'shutdown' SIGTERM SIGINT SIGQUIT

# ==============================================================================
# FUNÇÕES DE HEALTH CHECK
# ==============================================================================

# Aguarda o Redis ficar disponível
wait_for_redis() {
    log_section "Aguardando Redis"
    log_info "Conectando ao Redis: ${REDIS_HOST}:${REDIS_PORT}"

    local elapsed=0

    until redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null | grep -q "PONG"; do
        elapsed=$((elapsed + WAIT_INTERVAL))
        if [ "$elapsed" -ge "$MAX_WAIT" ]; then
            log_error "Redis não disponível após ${MAX_WAIT}s. Abortando."
            exit 1
        fi
        log_warn "Redis não disponível. Aguardando... (${elapsed}/${MAX_WAIT}s)"
        sleep $WAIT_INTERVAL
    done

    log_info "✓ Redis disponível em ${REDIS_HOST}:${REDIS_PORT}"
}

# Aguarda o PostgreSQL ficar disponível
wait_for_postgres() {
    log_section "Aguardando PostgreSQL"
    log_info "Conectando ao PostgreSQL: ${PG_HOST}:${PG_PORT}"

    local elapsed=0

    until pg_isready -h "$PG_HOST" -p "$PG_PORT" -q 2>/dev/null; do
        elapsed=$((elapsed + WAIT_INTERVAL))
        if [ "$elapsed" -ge "$MAX_WAIT" ]; then
            log_error "PostgreSQL não disponível após ${MAX_WAIT}s. Abortando."
            exit 1
        fi
        log_warn "PostgreSQL não disponível. Aguardando... (${elapsed}/${MAX_WAIT}s)"
        sleep $WAIT_INTERVAL
    done

    log_info "✓ PostgreSQL disponível em ${PG_HOST}:${PG_PORT}"
}

# ==============================================================================
# FUNÇÕES DE INICIALIZAÇÃO
# ==============================================================================

# Executa migrações Alembic
run_migrations() {
    log_section "Migrações Alembic"

    # Aguarda 2s adicionais para garantir que o schema esteja estável
    sleep 2

    log_info "Executando migrações Alembic..."

    if alembic -c /app/database/alembic.ini upgrade head; then
        log_info "✓ Migrações aplicadas com sucesso"
    else
        local exit_code=$?
        log_error "Falha nas migrações Alembic (exit code: $exit_code)"
        exit "$exit_code"
    fi
}

# Instala navegadores Playwright se necessário
install_playwright_browsers() {
    if [ "${INSTALL_PLAYWRIGHT:-false}" = "true" ]; then
        log_section "Playwright Browsers"
        log_info "Instalando navegadores Playwright (chromium)..."

        if playwright install chromium --with-deps; then
            log_info "✓ Navegadores Playwright instalados"
        else
            log_warn "Falha ao instalar navegadores Playwright (operação continuará sem JS rendering)"
        fi
    fi
}

# Pré-aquece o worker (verifica imports críticos)
warmup_worker() {
    log_section "Verificação de Imports"
    log_info "Verificando módulos críticos do worker..."

    if python -c "
import sys
erros = []

try:
    from worker.celery_config import app
    print('  ✓ celery_config importado')
except Exception as e:
    erros.append(f'  ✗ celery_config: {e}')

try:
    from worker.tasks import scrape_url, update_proxy_pool, cleanup_old_jobs
    print('  ✓ tasks importadas')
except Exception as e:
    erros.append(f'  ✗ tasks: {e}')

try:
    from worker.events import EventPublisher
    print('  ✓ events importado')
except Exception as e:
    erros.append(f'  ✗ events: {e}')

try:
    from worker.scheduler import run_dynamic_schedules
    print('  ✓ scheduler importado')
except Exception as e:
    erros.append(f'  ✗ scheduler: {e}')

if erros:
    print('Erros encontrados:')
    for erro in erros:
        print(erro)
    sys.exit(1)

print('Todos os módulos verificados com sucesso.')
" 2>&1; then
        log_info "✓ Todos os módulos carregados corretamente"
    else
        log_error "Falha ao carregar módulos do worker. Verifique os logs acima."
        exit 1
    fi
}

# ==============================================================================
# INICIALIZAÇÃO DOS SERVIÇOS
# ==============================================================================

start_worker() {
    log_section "Iniciando Celery Worker"
    log_info "ROLE=worker"
    log_info "App: ${CELERY_APP}"
    log_info "Concorrência: ${CELERY_CONCURRENCY}"
    log_info "Filas: ${CELERY_QUEUES}"
    log_info "Log level: ${CELERY_LOG_LEVEL}"

    exec celery \
        -A "${CELERY_APP}" \
        worker \
        --loglevel="${CELERY_LOG_LEVEL}" \
        --concurrency="${CELERY_CONCURRENCY}" \
        -Q "${CELERY_QUEUES}" \
        --hostname="${CELERY_WORKER_HOSTNAME}" \
        --without-gossip \
        --without-mingle \
        --without-heartbeat \
        -Ofair \
        &

    CELERY_PID=$!
    log_info "Worker Celery iniciado com PID=$CELERY_PID"
    wait "$CELERY_PID"
}

start_beat() {
    log_section "Iniciando Celery Beat"
    log_info "ROLE=beat"
    log_info "App: ${CELERY_APP}"
    log_info "Log level: ${CELERY_LOG_LEVEL}"

    exec celery \
        -A "${CELERY_APP}" \
        beat \
        --loglevel="${CELERY_LOG_LEVEL}" \
        --scheduler celery.beat:PersistentScheduler \
        --schedule /tmp/celerybeat-schedule \
        --pidfile /tmp/celerybeat.pid \
        &

    CELERY_PID=$!
    log_info "Celery Beat iniciado com PID=$CELERY_PID"
    wait "$CELERY_PID"
}

start_flower() {
    log_section "Iniciando Flower (Monitoramento)"

    FLOWER_PORT="${FLOWER_PORT:-5555}"
    FLOWER_BASIC_AUTH="${FLOWER_BASIC_AUTH:-admin:flowerpass}"

    log_info "Flower disponível em http://0.0.0.0:${FLOWER_PORT}"

    exec celery \
        -A "${CELERY_APP}" \
        flower \
        --port="${FLOWER_PORT}" \
        --basic_auth="${FLOWER_BASIC_AUTH}" \
        --url_prefix="${FLOWER_URL_PREFIX:-}" \
        &

    CELERY_PID=$!
    log_info "Flower iniciado com PID=$CELERY_PID"
    wait "$CELERY_PID"
}

start_all() {
    log_section "Iniciando Worker + Beat (modo desenvolvimento)"
    log_warn "ATENÇÃO: Modo 'all' não recomendado para produção!"

    # Inicia o beat em background
    celery \
        -A "${CELERY_APP}" \
        beat \
        --loglevel="${CELERY_LOG_LEVEL}" \
        --scheduler celery.beat:PersistentScheduler \
        --schedule /tmp/celerybeat-schedule \
        --pidfile /tmp/celerybeat.pid \
        --detach

    log_info "Celery Beat iniciado em background"

    # Inicia o worker em foreground
    start_worker
}

# ==============================================================================
# MAIN
# ==============================================================================

main() {
    log_section "WebScraper Worker Startup"
    log_info "Role: ${ROLE}"
    log_info "Python: $(python --version 2>&1)"
    log_info "Celery: $(celery --version 2>&1 | head -1)"

    # Fase 1: Aguarda serviços dependentes
    wait_for_redis
    wait_for_postgres

    # Fase 2: Executa migrações (somente nos roles que precisam)
    if [ "${RUN_MIGRATIONS:-true}" = "true" ] && [ "$ROLE" != "flower" ]; then
        run_migrations
    fi

    # Fase 3: Instala Playwright se configurado
    install_playwright_browsers

    # Fase 4: Verifica módulos Python
    warmup_worker

    # Fase 5: Inicia o serviço conforme o ROLE
    log_section "Iniciando Serviço: ${ROLE}"

    case "$ROLE" in
        worker)
            start_worker
            ;;
        beat)
            start_beat
            ;;
        flower)
            start_flower
            ;;
        all)
            start_all
            ;;
        *)
            log_error "ROLE desconhecido: '${ROLE}'. Use: worker, beat, flower, all"
            exit 1
            ;;
    esac
}

main "$@"
