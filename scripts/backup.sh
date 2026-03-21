#!/bin/bash
# ==============================================================================
# backup.sh — Backup automatizado do PostgreSQL
# WebScraper Pro — Script de backup com retenção
#
# Uso:
#   bash scripts/backup.sh                    # Execução manual
#   Cron: 0 2 * * * /opt/webscraper/scripts/backup.sh  # Diário às 02:00
#
# O script cria backups comprimidos com gzip e mantém apenas os últimos 7
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# CONFIGURAÇÃO
# Carrega variáveis do .env se disponível
# ------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "${SCRIPT_DIR}")"

# Carregar .env se existir
if [ -f "${APP_DIR}/.env" ]; then
    # Exportar apenas variáveis do banco de dados (sem linhas comentadas ou vazias)
    set -a
    # shellcheck disable=SC1090
    source <(grep -E "^(POSTGRES_|DB_)" "${APP_DIR}/.env" 2>/dev/null || true)
    set +a
fi

# Configurações do banco (fallback para valores padrão se não definido no .env)
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-webscraper_db}"
DB_USER="${POSTGRES_USER:-webscraper_user}"
DB_PASSWORD="${POSTGRES_PASSWORD:-}"

# Configurações do backup
BACKUP_DIR="${APP_DIR}/backups"
RETENCAO_DIAS=7               # Manter backups dos últimos N dias
PROJETO="webscraper"

# Configurações de notificação (opcional)
SLACK_WEBHOOK="${SLACK_WEBHOOK_URL:-}"   # URL do webhook Slack (opcional)
NOTIFY_ON_SUCCESS=false                 # Notificar no Slack em sucesso
NOTIFY_ON_ERROR=true                    # Notificar no Slack em erro

# Arquivo de log
LOG_DIR="${APP_DIR}/logs"
LOG_FILE="${LOG_DIR}/backup.log"

# Cores
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
AZUL='\033[0;34m'
VERMELHO='\033[0;31m'
RESET='\033[0m'

# ------------------------------------------------------------------------------
# FUNÇÕES
# ------------------------------------------------------------------------------

# Escreve no log e no terminal
log() {
    local NIVEL="$1"
    local MENSAGEM="$2"
    local TIMESTAMP
    TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
    
    # Log em arquivo
    echo "[${TIMESTAMP}] [${NIVEL}] ${MENSAGEM}" >> "${LOG_FILE}"
    
    # Output no terminal com cores
    case "${NIVEL}" in
        "INFO")  echo -e "${AZUL}[${TIMESTAMP}] ℹ ${MENSAGEM}${RESET}" ;;
        "OK")    echo -e "${VERDE}[${TIMESTAMP}] ✓ ${MENSAGEM}${RESET}" ;;
        "WARN")  echo -e "${AMARELO}[${TIMESTAMP}] ⚠ ${MENSAGEM}${RESET}" ;;
        "ERRO")  echo -e "${VERMELHO}[${TIMESTAMP}] ✗ ${MENSAGEM}${RESET}" >&2 ;;
    esac
}

# Envia notificação para Slack
notificar_slack() {
    local STATUS="$1"
    local MENSAGEM="$2"
    
    if [ -z "${SLACK_WEBHOOK}" ]; then
        return  # Webhook não configurado
    fi
    
    local COR
    local ICONE
    
    if [ "${STATUS}" = "sucesso" ]; then
        COR="good"
        ICONE=":white_check_mark:"
    else
        COR="danger"
        ICONE=":x:"
    fi
    
    curl -s -X POST "${SLACK_WEBHOOK}" \
        -H "Content-Type: application/json" \
        -d "{
            \"attachments\": [{
                \"color\": \"${COR}\",
                \"title\": \"${ICONE} Backup WebScraper — ${STATUS^}\",
                \"text\": \"${MENSAGEM}\",
                \"footer\": \"$(hostname) | $(date '+%d/%m/%Y %H:%M')\",
                \"ts\": $(date +%s)
            }]
        }" &>/dev/null || true
}

# Verifica pré-requisitos
verificar_prerequisitos() {
    log "INFO" "Verificando pré-requisitos..."
    
    # Verificar se docker está disponível
    if ! command -v docker &>/dev/null; then
        log "ERRO" "Docker não encontrado. Instale o Docker primeiro."
        exit 1
    fi
    
    # Criar diretórios necessários
    mkdir -p "${BACKUP_DIR}" "${LOG_DIR}"
    
    log "OK" "Pré-requisitos verificados"
}

# Verifica conexão com banco de dados
verificar_banco() {
    log "INFO" "Verificando conexão com PostgreSQL..."
    
    # Testar conexão via container Docker
    if ! docker compose -f "${APP_DIR}/docker-compose.yml" \
         exec -T postgres \
         pg_isready -U "${DB_USER}" -d "${DB_NAME}" &>/dev/null; then
        log "ERRO" "PostgreSQL não está acessível"
        notificar_slack "erro" "PostgreSQL offline — backup não realizado"
        exit 1
    fi
    
    log "OK" "PostgreSQL está online"
}

# Executa o backup
realizar_backup() {
    local TIMESTAMP
    TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
    local NOME_ARQUIVO="backup_${PROJETO}_${TIMESTAMP}.sql.gz"
    local CAMINHO_COMPLETO="${BACKUP_DIR}/${NOME_ARQUIVO}"
    
    log "INFO" "Iniciando backup → ${NOME_ARQUIVO}"
    
    # Tempo de início para calcular duração
    local INICIO
    INICIO=$(date +%s)
    
    # Executar pg_dump via container Docker e comprimir com gzip
    # A senha é passada via PGPASSWORD para evitar prompt interativo
    if docker compose -f "${APP_DIR}/docker-compose.yml" \
       exec -T -e "PGPASSWORD=${DB_PASSWORD}" postgres \
       pg_dump \
           --username="${DB_USER}" \
           --dbname="${DB_NAME}" \
           --format=plain \
           --no-password \
           --verbose \
           2>>"${LOG_FILE}" \
       | gzip -9 > "${CAMINHO_COMPLETO}"; then
        
        local FIM
        FIM=$(date +%s)
        local DURACAO=$((FIM - INICIO))
        local TAMANHO
        TAMANHO=$(du -sh "${CAMINHO_COMPLETO}" | cut -f1)
        
        log "OK" "Backup criado: ${NOME_ARQUIVO} (${TAMANHO}, ${DURACAO}s)"
        
        # Salvar metadados do backup
        cat >> "${LOG_FILE}" << EOF
[${TIMESTAMP}] METADADOS: arquivo=${NOME_ARQUIVO} tamanho=${TAMANHO} duracao=${DURACAO}s banco=${DB_NAME}
EOF
        
        # Verificar integridade do arquivo
        if gzip -t "${CAMINHO_COMPLETO}" 2>/dev/null; then
            log "OK" "Integridade do arquivo verificada (gzip válido)"
        else
            log "WARN" "Arquivo pode estar corrompido — verificar manualmente"
        fi
        
        echo "${CAMINHO_COMPLETO}"
        return 0
    else
        log "ERRO" "Falha ao criar backup"
        rm -f "${CAMINHO_COMPLETO}"  # Remover arquivo incompleto
        return 1
    fi
}

# Remove backups antigos mantendo apenas os últimos N
limpar_backups_antigos() {
    log "INFO" "Removendo backups com mais de ${RETENCAO_DIAS} dias..."
    
    local REMOVIDOS=0
    
    # Listar arquivos de backup com mais de N dias e remover
    while IFS= read -r arquivo; do
        if [ -f "${arquivo}" ]; then
            rm -f "${arquivo}"
            log "INFO" "  Removido: $(basename "${arquivo}")"
            REMOVIDOS=$((REMOVIDOS + 1))
        fi
    done < <(find "${BACKUP_DIR}" -name "backup_${PROJETO}_*.sql.gz" \
             -mtime "+${RETENCAO_DIAS}" 2>/dev/null)
    
    if [ $REMOVIDOS -gt 0 ]; then
        log "OK" "${REMOVIDOS} backup(s) antigo(s) removido(s)"
    else
        log "INFO" "Nenhum backup antigo para remover"
    fi
    
    # Listar backups disponíveis
    log "INFO" "Backups disponíveis:"
    local CONTADOR=0
    while IFS= read -r arquivo; do
        local TAMANHO
        TAMANHO=$(du -sh "${arquivo}" 2>/dev/null | cut -f1 || echo "?")
        local DATA_MOD
        DATA_MOD=$(date -r "${arquivo}" '+%d/%m/%Y %H:%M' 2>/dev/null || echo "?")
        log "INFO" "  $(basename "${arquivo}") | ${TAMANHO} | ${DATA_MOD}"
        CONTADOR=$((CONTADOR + 1))
    done < <(find "${BACKUP_DIR}" -name "backup_${PROJETO}_*.sql.gz" \
             -type f | sort -r 2>/dev/null)
    
    log "INFO" "Total: ${CONTADOR} backup(s)"
}

# Rotacionar logs antigos
rotacionar_logs() {
    # Manter log com no máximo 1000 linhas
    if [ -f "${LOG_FILE}" ] && [ "$(wc -l < "${LOG_FILE}")" -gt 1000 ]; then
        tail -n 500 "${LOG_FILE}" > "${LOG_FILE}.tmp"
        mv "${LOG_FILE}.tmp" "${LOG_FILE}"
        log "INFO" "Log rotacionado (mantidas últimas 500 linhas)"
    fi
}

# ------------------------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ------------------------------------------------------------------------------
main() {
    echo ""
    log "INFO" "===== Iniciando backup do WebScraper Pro ====="
    log "INFO" "Banco: ${DB_NAME} | Host: ${DB_HOST}:${DB_PORT}"
    
    verificar_prerequisitos
    verificar_banco
    
    # Realizar backup
    if ARQUIVO_BACKUP=$(realizar_backup); then
        limpar_backups_antigos
        rotacionar_logs
        
        local TAMANHO
        TAMANHO=$(du -sh "${ARQUIVO_BACKUP}" | cut -f1)
        
        log "OK" "===== Backup concluído com sucesso! ====="
        log "OK" "Arquivo: ${ARQUIVO_BACKUP} (${TAMANHO})"
        
        if [ "${NOTIFY_ON_SUCCESS}" = "true" ]; then
            notificar_slack "sucesso" \
                "Backup realizado: $(basename "${ARQUIVO_BACKUP}") | Tamanho: ${TAMANHO}"
        fi
        
        exit 0
    else
        log "ERRO" "===== Backup FALHOU! ====="
        
        notificar_slack "erro" \
            "FALHA no backup do banco ${DB_NAME} em $(hostname)"
        
        exit 1
    fi
}

main "$@"
