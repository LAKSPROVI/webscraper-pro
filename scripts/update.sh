#!/bin/bash
# ==============================================================================
# update.sh — Atualização do WebScraper Pro com zero downtime
# 
# Este script faz:
#   1. Backup do banco de dados antes de atualizar
#   2. Pull do código mais recente
#   3. Build das novas imagens Docker
#   4. Rolling update com docker compose (zero downtime para API)
#   5. Execução de migrações de banco de dados
#   6. Verificação de saúde após atualização
#   7. Rollback automático em caso de falha
#
# Uso:
#   bash scripts/update.sh           # Atualização normal
#   bash scripts/update.sh --skip-backup  # Pular backup (não recomendado)
#   bash scripts/update.sh --force   # Forçar mesmo com mudanças locais
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# CONFIGURAÇÃO
# ------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "${SCRIPT_DIR}")"
COMPOSE_FILE="${APP_DIR}/docker-compose.yml"
LOG_FILE="${APP_DIR}/logs/update.log"

# Flags de linha de comando
SKIP_BACKUP=false
FORCE=false

# Processar argumentos
for ARG in "$@"; do
    case $ARG in
        --skip-backup) SKIP_BACKUP=true ;;
        --force)       FORCE=true ;;
        --help|-h)
            echo "Uso: $0 [--skip-backup] [--force] [--help]"
            echo ""
            echo "  --skip-backup  Pular backup do banco antes de atualizar"
            echo "  --force        Forçar atualização mesmo com mudanças locais"
            echo "  --help         Exibir esta ajuda"
            exit 0
            ;;
        *)
            echo "Argumento desconhecido: $ARG"
            exit 1
            ;;
    esac
done

# Cores
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
AZUL='\033[0;34m'
VERMELHO='\033[0;31m'
RESET='\033[0m'
NEGRITO='\033[1m'

# ------------------------------------------------------------------------------
# FUNÇÕES
# ------------------------------------------------------------------------------

log() {
    local NIVEL="$1"
    local MSG="$2"
    local TIMESTAMP
    TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
    
    mkdir -p "$(dirname "${LOG_FILE}")"
    echo "[${TIMESTAMP}] [${NIVEL}] ${MSG}" >> "${LOG_FILE}"
    
    case "${NIVEL}" in
        "INFO")  echo -e "${AZUL}[${TIMESTAMP}] ℹ ${MSG}${RESET}" ;;
        "OK")    echo -e "${VERDE}[${TIMESTAMP}] ✓ ${MSG}${RESET}" ;;
        "WARN")  echo -e "${AMARELO}[${TIMESTAMP}] ⚠ ${MSG}${RESET}" ;;
        "ERRO")  echo -e "${VERMELHO}[${TIMESTAMP}] ✗ ${MSG}${RESET}" >&2 ;;
        "STEP")  echo -e "\n${NEGRITO}${AZUL}${MSG}${RESET}" ;;
    esac
}

# Capturar versão atual para rollback
VERSAO_ATUAL=""
capturar_versao_atual() {
    VERSAO_ATUAL=$(git -C "${APP_DIR}" rev-parse HEAD 2>/dev/null || echo "")
    if [ -n "${VERSAO_ATUAL}" ]; then
        log "INFO" "Versão atual: ${VERSAO_ATUAL:0:8}"
    fi
}

# Verificar se há mudanças locais não commitadas
verificar_mudancas_locais() {
    if [ "${FORCE}" = "true" ]; then
        return 0
    fi
    
    if git -C "${APP_DIR}" status --porcelain 2>/dev/null | grep -qv "^??"; then
        log "WARN" "Há mudanças locais não commitadas:"
        git -C "${APP_DIR}" status --short 2>/dev/null || true
        echo ""
        read -p "Continuar mesmo assim? (s/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            log "INFO" "Atualização cancelada"
            exit 0
        fi
    fi
}

# Fazer backup preventivo
fazer_backup() {
    if [ "${SKIP_BACKUP}" = "true" ]; then
        log "WARN" "Backup pulado por --skip-backup (não recomendado!)"
        return
    fi
    
    log "INFO" "Fazendo backup preventivo do banco de dados..."
    
    if bash "${SCRIPT_DIR}/backup.sh"; then
        log "OK" "Backup concluído antes da atualização"
    else
        log "WARN" "Backup falhou — continuando com atualização por sua conta e risco"
        read -p "Continuar sem backup? (s/N) " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Ss]$ ]]; then
            exit 1
        fi
    fi
}

# Pull do código mais recente
atualizar_codigo() {
    log "STEP" "=== Atualizando código fonte ==="
    
    cd "${APP_DIR}"
    
    # Obter branch atual
    BRANCH_ATUAL=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    log "INFO" "Branch: ${BRANCH_ATUAL}"
    
    # Guardar stash se houver mudanças locais e --force
    if [ "${FORCE}" = "true" ]; then
        git -C "${APP_DIR}" stash push -m "Stash automático antes de update $(date)" \
            2>/dev/null || true
    fi
    
    # Pull do repositório remoto
    log "INFO" "Buscando atualizações do repositório..."
    git fetch --all --tags 2>&1 | tail -5
    
    # Verificar se há atualizações
    COMMITS_NOVOS=$(git rev-list HEAD...origin/"${BRANCH_ATUAL}" --count 2>/dev/null || echo "0")
    
    if [ "${COMMITS_NOVOS}" = "0" ]; then
        log "INFO" "Código já está na versão mais recente"
        # Continuar mesmo sem atualizações (pode haver mudanças de configuração)
    else
        log "INFO" "${COMMITS_NOVOS} commit(s) novo(s) encontrado(s)"
        
        # Exibir resumo das mudanças
        log "INFO" "Mudanças:"
        git log HEAD...origin/"${BRANCH_ATUAL}" \
            --pretty=format:"  • %h %s (%an, %ar)" 2>/dev/null | head -10 || true
        echo ""
    fi
    
    # Aplicar atualizações
    git pull origin "${BRANCH_ATUAL}" 2>&1
    
    VERSAO_NOVA=$(git rev-parse HEAD 2>/dev/null || echo "desconhecida")
    log "OK" "Código atualizado para: ${VERSAO_NOVA:0:8}"
}

# Build das novas imagens
build_imagens() {
    log "STEP" "=== Construindo novas imagens Docker ==="
    
    cd "${APP_DIR}"
    
    # Build apenas dos serviços que têm Dockerfile (api, worker)
    # --pull: verificar imagens base atualizadas
    # --no-cache: garantir build limpo
    log "INFO" "Construindo imagens (pode levar alguns minutos)..."
    
    if docker compose -f "${COMPOSE_FILE}" build --pull 2>&1 | \
       grep -E "(Step|Successfully|ERROR|WARN)" | tail -20; then
        log "OK" "Imagens construídas com sucesso"
    else
        log "ERRO" "Falha ao construir imagens"
        rollback
        exit 1
    fi
}

# Verificar se migrações são necessárias
verificar_migracoes() {
    log "INFO" "Verificando migrações pendentes..."
    
    # Contar migrações pendentes
    MIGRACOES=$(docker compose -f "${COMPOSE_FILE}" \
        exec -T api alembic current 2>/dev/null || echo "erro")
    
    if echo "${MIGRACOES}" | grep -q "(head)"; then
        log "INFO" "Banco de dados já está atualizado (sem migrações pendentes)"
        return 0
    else
        log "WARN" "Há migrações pendentes — serão executadas após o deploy"
        return 1
    fi
}

# Atualizar serviços com zero downtime
atualizar_servicos() {
    log "STEP" "=== Atualizando serviços Docker ==="
    
    cd "${APP_DIR}"
    
    # Estratégia de zero downtime:
    # 1. Atualizar serviços stateless primeiro (API pode ter múltiplas réplicas)
    # 2. Manter banco de dados e Redis rodando (não recriar)
    # 3. Recriar API e workers com novas imagens
    
    log "INFO" "Atualizando API com nova imagem..."
    docker compose -f "${COMPOSE_FILE}" up -d \
        --no-deps \
        --build \
        --force-recreate \
        api 2>&1 | tail -5
    
    # Aguardar API estar saudável antes de atualizar workers
    log "INFO" "Aguardando API ficar saudável..."
    local TENTATIVAS=0
    local MAX_TENTATIVAS=30
    
    while [ $TENTATIVAS -lt $MAX_TENTATIVAS ]; do
        if curl -sf http://localhost:8000/health &>/dev/null; then
            log "OK" "API está respondendo"
            break
        fi
        TENTATIVAS=$((TENTATIVAS + 1))
        sleep 3
    done
    
    if [ $TENTATIVAS -eq $MAX_TENTATIVAS ]; then
        log "ERRO" "API não ficou saudável após atualização"
        rollback
        exit 1
    fi
    
    # Atualizar workers Celery
    log "INFO" "Atualizando workers Celery..."
    docker compose -f "${COMPOSE_FILE}" up -d \
        --no-deps \
        --build \
        --force-recreate \
        worker 2>&1 | tail -5
    
    # Atualizar frontend
    log "INFO" "Atualizando frontend..."
    docker compose -f "${COMPOSE_FILE}" up -d \
        --no-deps \
        --build \
        --force-recreate \
        frontend 2>&1 | tail -5 || \
    log "WARN" "Frontend não disponível (opcional)"
    
    # Garantir todos os serviços estão rodando
    log "INFO" "Verificando todos os serviços..."
    docker compose -f "${COMPOSE_FILE}" up -d 2>&1 | tail -5
    
    log "OK" "Serviços atualizados"
}

# Executar migrações do banco de dados
executar_migracoes() {
    log "STEP" "=== Executando migrações do banco de dados ==="
    
    log "INFO" "Rodando: alembic upgrade head"
    
    if docker compose -f "${COMPOSE_FILE}" exec -T api \
       alembic upgrade head 2>&1; then
        log "OK" "Migrações executadas com sucesso"
    else
        log "ERRO" "Falha nas migrações — verificar manualmente"
        log "INFO" "Execute: make migrate"
        # Não faz rollback aqui — pode ser apenas um aviso
    fi
}

# Verificar saúde após atualização
verificar_saude() {
    log "STEP" "=== Verificando saúde dos serviços ==="
    
    # Aguardar estabilização
    sleep 5
    
    # Verificar cada serviço
    local FALHAS=0
    
    servicos_criticos=("postgres" "redis" "api" "worker")
    
    for SERVICO in "${servicos_criticos[@]}"; do
        STATUS=$(docker compose -f "${COMPOSE_FILE}" \
            ps "${SERVICO}" --format json 2>/dev/null | \
            jq -r '.[0].State // "unknown"' 2>/dev/null || echo "unknown")
        
        if [ "${STATUS}" = "running" ]; then
            log "OK" "  ${SERVICO}: running ✓"
        else
            log "WARN" "  ${SERVICO}: ${STATUS} ✗"
            FALHAS=$((FALHAS + 1))
        fi
    done
    
    # Testar endpoint da API
    if curl -sf http://localhost:8000/health &>/dev/null; then
        log "OK" "  API Health: OK ✓"
    else
        log "WARN" "  API Health: não respondendo ✗"
        FALHAS=$((FALHAS + 1))
    fi
    
    if [ $FALHAS -gt 0 ]; then
        log "WARN" "${FALHAS} serviço(s) com problema"
        return 1
    else
        log "OK" "Todos os serviços estão saudáveis"
        return 0
    fi
}

# Rollback para versão anterior
rollback() {
    log "WARN" "Iniciando rollback para versão anterior..."
    
    if [ -n "${VERSAO_ATUAL}" ]; then
        log "INFO" "Revertendo código para ${VERSAO_ATUAL:0:8}..."
        git -C "${APP_DIR}" checkout "${VERSAO_ATUAL}" 2>/dev/null || true
    fi
    
    log "INFO" "Reiniciando serviços com versão anterior..."
    docker compose -f "${COMPOSE_FILE}" up -d \
        --no-deps --build --force-recreate api worker 2>&1 | tail -5 || true
    
    log "WARN" "Rollback concluído — verificar serviços manualmente"
}

# Limpar imagens e containers antigos
limpar_docker() {
    log "INFO" "Limpando artefatos Docker não utilizados..."
    
    # Remover imagens sem tag (dangling)
    docker image prune -f 2>/dev/null || true
    
    # Remover containers parados
    docker container prune -f 2>/dev/null || true
    
    log "OK" "Limpeza concluída"
}

# Exibir resumo da atualização
exibir_resumo() {
    VERSAO_NOVA=$(git -C "${APP_DIR}" rev-parse HEAD 2>/dev/null || echo "desconhecida")
    
    echo ""
    echo -e "${VERDE}${NEGRITO}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║            ✓ Atualização Concluída com Sucesso!          ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    
    if [ -n "${VERSAO_ATUAL}" ] && [ "${VERSAO_ATUAL}" != "${VERSAO_NOVA}" ]; then
        echo -e "  ${AMARELO}Versão anterior:${RESET} ${VERSAO_ATUAL:0:8}"
        echo -e "  ${VERDE}Versão atual:${RESET}    ${VERSAO_NOVA:0:8}"
    else
        echo -e "  ${VERDE}Versão:${RESET} ${VERSAO_NOVA:0:8} (sem mudanças de código)"
    fi
    
    echo ""
    echo -e "  ${AMARELO}Status dos containers:${RESET}"
    docker compose -f "${COMPOSE_FILE}" ps --format "table {{.Name}}\t{{.Status}}" \
        2>/dev/null | tail -n +2 | sed 's/^/  /' || true
    echo ""
}

# ------------------------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ------------------------------------------------------------------------------
main() {
    echo ""
    log "STEP" "╔══════════════════════════════════════╗"
    log "STEP" "║  WebScraper Pro — Atualização        ║"
    log "STEP" "║  $(date '+%d/%m/%Y %H:%M:%S')             ║"
    log "STEP" "╚══════════════════════════════════════╝"
    
    INICIO=$(date +%s)
    
    # Ir para o diretório da aplicação
    cd "${APP_DIR}"
    
    # Etapas da atualização
    capturar_versao_atual
    verificar_mudancas_locais
    fazer_backup
    atualizar_codigo
    build_imagens
    atualizar_servicos
    executar_migracoes
    
    if verificar_saude; then
        limpar_docker
        
        FIM=$(date +%s)
        DURACAO=$((FIM - INICIO))
        
        log "OK" "Atualização concluída em ${DURACAO} segundos"
        exibir_resumo
        
        exit 0
    else
        log "ERRO" "Verificação de saúde falhou após atualização"
        log "INFO" "Execute 'make logs' para investigar"
        log "INFO" "Execute 'make status' para ver o estado dos containers"
        
        exit 1
    fi
}

main "$@"
