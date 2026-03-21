#!/bin/bash
# ==============================================================================
# setup_vps.sh — Configuração completa de VPS Ubuntu 22.04 do zero
# WebScraper Pro — Script de inicialização do servidor
#
# Uso: curl -sSL https://raw.githubusercontent.com/seu-repo/webscraper/main/scripts/setup_vps.sh | bash
# Ou:  bash scripts/setup_vps.sh
#
# REQUISITOS:
#   - Ubuntu 22.04 LTS (Jammy Jellyfish)
#   - Acesso root ou sudo
#   - Conexão com a internet
#   - Mínimo 1GB RAM (recomendado 2GB+)
# ==============================================================================

set -euo pipefail  # Sair em erro, variável não definida, ou falha em pipe

# ------------------------------------------------------------------------------
# VARIÁVEIS DE CONFIGURAÇÃO
# Edite conforme necessário antes de executar
# ------------------------------------------------------------------------------
REPO_URL="https://github.com/seu-usuario/webscraper.git"
APP_DIR="/opt/webscraper"
APP_USER="webscraper"
SWAP_SIZE="4G"               # Tamanho do swap (útil para VPS com pouca RAM)
DOCKER_COMPOSE_VERSION="v2.24.5"

# Portas liberadas no firewall
PORTAS_ABERTAS=(22 80 443 8000 3000 5555)

# Cores para output
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
AZUL='\033[0;34m'
VERMELHO='\033[0;31m'
RESET='\033[0m'
NEGRITO='\033[1m'

# ------------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ------------------------------------------------------------------------------

log() {
    echo -e "${VERDE}[$(date '+%H:%M:%S')] ✓ $1${RESET}"
}

info() {
    echo -e "${AZUL}[$(date '+%H:%M:%S')] ℹ $1${RESET}"
}

warn() {
    echo -e "${AMARELO}[$(date '+%H:%M:%S')] ⚠ $1${RESET}"
}

erro() {
    echo -e "${VERMELHO}[$(date '+%H:%M:%S')] ✗ ERRO: $1${RESET}" >&2
    exit 1
}

# Verifica se é root ou tem sudo
verificar_privilegios() {
    if [[ $EUID -ne 0 ]]; then
        if ! sudo -n true 2>/dev/null; then
            erro "Este script precisa ser executado como root ou com sudo"
        fi
        SUDO="sudo"
    else
        SUDO=""
    fi
}

# Banner inicial
banner() {
    echo ""
    echo -e "${AZUL}${NEGRITO}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║          WebScraper Pro — Setup VPS Ubuntu 22.04         ║"
    echo "║                 Configuração Automática                   ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo ""
    echo -e "  ${AMARELO}Servidor:${RESET} $(hostname)"
    echo -e "  ${AMARELO}IP:${RESET}       $(curl -s ifconfig.me 2>/dev/null || echo 'N/A')"
    echo -e "  ${AMARELO}Data:${RESET}     $(date '+%d/%m/%Y %H:%M:%S')"
    echo ""
}

# ------------------------------------------------------------------------------
# ETAPA 1: Atualização do Sistema
# ------------------------------------------------------------------------------
atualizar_sistema() {
    info "=== ETAPA 1/10: Atualizando sistema ==="
    
    # Configurar apt para não fazer perguntas interativas
    export DEBIAN_FRONTEND=noninteractive
    
    $SUDO apt-get update -qq
    $SUDO apt-get upgrade -y -qq \
        -o Dpkg::Options::="--force-confdef" \
        -o Dpkg::Options::="--force-confold"
    
    # Instalar dependências básicas
    $SUDO apt-get install -y -qq \
        curl wget git htop nano vim \
        ca-certificates gnupg lsb-release \
        apt-transport-https software-properties-common \
        unzip jq net-tools ufw \
        python3 python3-pip
    
    log "Sistema atualizado e dependências instaladas"
}

# ------------------------------------------------------------------------------
# ETAPA 2: Instalar Docker + Docker Compose v2
# ------------------------------------------------------------------------------
instalar_docker() {
    info "=== ETAPA 2/10: Instalando Docker ==="
    
    # Verificar se Docker já está instalado
    if command -v docker &>/dev/null; then
        warn "Docker já está instalado: $(docker --version)"
        return
    fi
    
    # Remover versões antigas se existirem
    $SUDO apt-get remove -y -qq docker docker-engine docker.io containerd runc 2>/dev/null || true
    
    # Adicionar repositório oficial do Docker
    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg
    
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    $SUDO apt-get update -qq
    $SUDO apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    
    # Habilitar e iniciar Docker
    $SUDO systemctl enable docker
    $SUDO systemctl start docker
    
    # Adicionar usuário atual ao grupo docker (evita precisar de sudo)
    $SUDO usermod -aG docker "$USER" 2>/dev/null || true
    
    # Verificar instalação
    DOCKER_VERSION=$(docker --version)
    COMPOSE_VERSION=$(docker compose version)
    
    log "Docker instalado: ${DOCKER_VERSION}"
    log "Docker Compose: ${COMPOSE_VERSION}"
    
    # Configurar daemon Docker com otimizações
    cat > /tmp/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-address-pools": [
    {"base": "172.20.0.0/16", "size": 24}
  ]
}
EOF
    $SUDO mv /tmp/daemon.json /etc/docker/daemon.json
    $SUDO systemctl restart docker
    
    log "Docker configurado com limites de log"
}

# ------------------------------------------------------------------------------
# ETAPA 3: Configurar Firewall UFW
# ------------------------------------------------------------------------------
configurar_firewall() {
    info "=== ETAPA 3/10: Configurando firewall UFW ==="
    
    # Garantir que SSH (porta 22) está liberada ANTES de ativar o firewall
    $SUDO ufw allow 22/tcp comment "SSH" || true
    
    # Liberar todas as portas necessárias
    for PORTA in "${PORTAS_ABERTAS[@]}"; do
        $SUDO ufw allow "${PORTA}/tcp" comment "WebScraper" || true
        log "Porta ${PORTA}/tcp liberada"
    done
    
    # Ativar UFW (não interativo)
    $SUDO ufw --force enable
    
    # Exibir status
    $SUDO ufw status verbose
    
    log "Firewall configurado"
}

# ------------------------------------------------------------------------------
# ETAPA 4: Configurar Swap de 4GB
# Essencial para VPS com pouca RAM (1-2GB)
# ------------------------------------------------------------------------------
configurar_swap() {
    info "=== ETAPA 4/10: Configurando swap de ${SWAP_SIZE} ==="
    
    # Verificar se swap já existe
    if swapon --show | grep -q "/swapfile"; then
        warn "Swap já configurado:"
        swapon --show
        return
    fi
    
    # Criar arquivo de swap
    $SUDO fallocate -l "${SWAP_SIZE}" /swapfile
    $SUDO chmod 600 /swapfile
    $SUDO mkswap /swapfile
    $SUDO swapon /swapfile
    
    # Tornar permanente no fstab
    if ! grep -q "/swapfile" /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab
    fi
    
    # Otimizar parâmetros de memória virtual
    # swappiness=10: usar swap apenas quando necessário
    # vfs_cache_pressure=50: manter cache de arquivos em memória
    $SUDO sysctl vm.swappiness=10
    $SUDO sysctl vm.vfs_cache_pressure=50
    
    if ! grep -q "vm.swappiness" /etc/sysctl.conf; then
        echo "vm.swappiness=10" | $SUDO tee -a /etc/sysctl.conf
        echo "vm.vfs_cache_pressure=50" | $SUDO tee -a /etc/sysctl.conf
    fi
    
    # Exibir informações de memória
    free -h
    
    log "Swap de ${SWAP_SIZE} configurado"
}

# ------------------------------------------------------------------------------
# ETAPA 5: Criar usuário da aplicação (opcional, por segurança)
# ------------------------------------------------------------------------------
criar_usuario_app() {
    info "=== ETAPA 5/10: Configurando usuário da aplicação ==="
    
    # Criar usuário se não existir
    if ! id "${APP_USER}" &>/dev/null; then
        $SUDO useradd -m -s /bin/bash -G docker "${APP_USER}"
        log "Usuário '${APP_USER}' criado e adicionado ao grupo docker"
    else
        warn "Usuário '${APP_USER}' já existe"
        # Garantir que está no grupo docker
        $SUDO usermod -aG docker "${APP_USER}" 2>/dev/null || true
    fi
}

# ------------------------------------------------------------------------------
# ETAPA 6: Clonar o Repositório
# ------------------------------------------------------------------------------
clonar_repositorio() {
    info "=== ETAPA 6/10: Clonando repositório ==="
    
    if [ -d "${APP_DIR}" ]; then
        warn "Diretório ${APP_DIR} já existe, fazendo pull..."
        cd "${APP_DIR}" && git pull
    else
        $SUDO git clone "${REPO_URL}" "${APP_DIR}"
        $SUDO chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}" 2>/dev/null || true
        cd "${APP_DIR}"
    fi
    
    log "Repositório em: ${APP_DIR}"
}

# ------------------------------------------------------------------------------
# ETAPA 7: Configurar variáveis de ambiente
# ------------------------------------------------------------------------------
configurar_env() {
    info "=== ETAPA 7/10: Configurando variáveis de ambiente ==="
    
    cd "${APP_DIR}"
    
    # Copiar template se .env não existir
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            log ".env criado a partir do .env.example"
        else
            warn ".env.example não encontrado, criando .env básico"
            touch .env
        fi
    else
        warn ".env já existe, mantendo configurações atuais"
        return
    fi
    
    # Gerar senhas aleatórias seguras (32 caracteres hexadecimais)
    gerar_senha() {
        openssl rand -hex 32
    }
    
    POSTGRES_PASSWORD=$(gerar_senha)
    SECRET_KEY=$(gerar_senha)
    REDIS_PASSWORD=$(gerar_senha)
    FLOWER_PASSWORD=$(gerar_senha)
    GRAFANA_PASSWORD=$(gerar_senha)
    
    # Substituir senhas no .env
    sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${POSTGRES_PASSWORD}/" .env
    sed -i "s/SECRET_KEY=.*/SECRET_KEY=${SECRET_KEY}/" .env
    sed -i "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=${REDIS_PASSWORD}/" .env
    sed -i "s/FLOWER_PASSWORD=.*/FLOWER_PASSWORD=${FLOWER_PASSWORD}/" .env
    sed -i "s/GRAFANA_PASSWORD=.*/GRAFANA_PASSWORD=${GRAFANA_PASSWORD}/" .env
    
    # Configurar URL base com IP público
    IP_PUBLICO=$(curl -s ifconfig.me 2>/dev/null || echo "localhost")
    sed -i "s/API_BASE_URL=.*/API_BASE_URL=http:\/\/${IP_PUBLICO}:8000/" .env
    
    log "Senhas geradas aleatoriamente e salvas no .env"
    warn "IMPORTANTE: Salve as senhas geradas! Elas estão em ${APP_DIR}/.env"
    
    # Salvar senhas em arquivo separado para consulta inicial
    cat > /root/webscraper_credentials.txt << EOF
WebScraper Pro — Credenciais Geradas em $(date)
================================================
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
SECRET_KEY:        ${SECRET_KEY}
REDIS_PASSWORD:    ${REDIS_PASSWORD}
FLOWER_PASSWORD:   ${FLOWER_PASSWORD}
GRAFANA_PASSWORD:  ${GRAFANA_PASSWORD}
IP Público:        ${IP_PUBLICO}
================================================
GUARDE ESTE ARQUIVO EM LOCAL SEGURO!
EOF
    chmod 600 /root/webscraper_credentials.txt
    log "Credenciais salvas em /root/webscraper_credentials.txt"
}

# ------------------------------------------------------------------------------
# ETAPA 8: Subir a stack Docker Compose
# ------------------------------------------------------------------------------
subir_stack() {
    info "=== ETAPA 8/10: Subindo a stack Docker Compose ==="
    
    cd "${APP_DIR}"
    
    # Build das imagens
    info "Construindo imagens Docker (pode levar alguns minutos)..."
    docker compose build --no-cache
    
    # Subir serviços em background
    info "Iniciando serviços..."
    docker compose up -d
    
    log "Stack iniciada"
}

# ------------------------------------------------------------------------------
# ETAPA 9: Aguardar serviços ficarem saudáveis
# ------------------------------------------------------------------------------
aguardar_servicos() {
    info "=== ETAPA 9/10: Aguardando serviços ficarem saudáveis ==="
    
    MAX_TENTATIVAS=30
    INTERVALO=5
    
    servicos=("postgres" "redis" "api")
    
    for servico in "${servicos[@]}"; do
        info "Aguardando ${servico}..."
        tentativas=0
        
        while [ $tentativas -lt $MAX_TENTATIVAS ]; do
            STATUS=$(docker compose ps "${servico}" --format json 2>/dev/null | \
                    jq -r '.[0].Health // "starting"' 2>/dev/null || echo "checking")
            
            if [[ "${STATUS}" == "healthy" ]] || [[ "${STATUS}" == "running" ]]; then
                log "${servico} está saudável"
                break
            fi
            
            tentativas=$((tentativas + 1))
            info "  ${servico}: ${STATUS} (tentativa ${tentativas}/${MAX_TENTATIVAS})"
            sleep $INTERVALO
        done
        
        if [ $tentativas -eq $MAX_TENTATIVAS ]; then
            warn "${servico} pode não estar totalmente pronto"
        fi
    done
    
    # Aguardar API responder
    info "Testando endpoint de saúde da API..."
    tentativas=0
    while [ $tentativas -lt $MAX_TENTATIVAS ]; do
        if curl -sf http://localhost:8000/health &>/dev/null; then
            log "API respondendo em http://localhost:8000/health"
            break
        fi
        tentativas=$((tentativas + 1))
        sleep $INTERVALO
    done
    
    # Rodar migrações do banco
    info "Rodando migrações do banco de dados..."
    docker compose exec -T api alembic upgrade head 2>/dev/null || \
        warn "Migrações podem precisar ser rodadas manualmente: make migrate"
}

# ------------------------------------------------------------------------------
# ETAPA 10: Configurar auto-reinício e exibir resumo
# ------------------------------------------------------------------------------
finalizar() {
    info "=== ETAPA 10/10: Finalizando configuração ==="
    
    # Configurar Docker para iniciar com o sistema
    $SUDO systemctl enable docker
    
    # Criar script de início automático do webscraper
    cat > /etc/systemd/system/webscraper.service << EOF
[Unit]
Description=WebScraper Pro Docker Stack
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0
User=root

[Install]
WantedBy=multi-user.target
EOF
    $SUDO systemctl enable webscraper.service
    
    log "WebScraper configurado para iniciar com o sistema"
    
    # Resumo final
    IP_PUBLICO=$(curl -s ifconfig.me 2>/dev/null || echo "localhost")
    
    echo ""
    echo -e "${VERDE}${NEGRITO}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║            ✓ Setup Concluído com Sucesso!                ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
    echo ""
    echo -e "  ${AMARELO}URLs de Acesso:${RESET}"
    echo -e "  🚀 API REST:       ${AZUL}http://${IP_PUBLICO}:8000${RESET}"
    echo -e "  📚 Documentação:   ${AZUL}http://${IP_PUBLICO}:8000/docs${RESET}"
    echo -e "  💐 Flower:         ${AZUL}http://${IP_PUBLICO}:5555${RESET}"
    echo -e "  📊 Grafana:        ${AZUL}http://${IP_PUBLICO}:3000${RESET}"
    echo -e "  🌐 Frontend:       ${AZUL}http://${IP_PUBLICO}:3001${RESET}"
    echo ""
    echo -e "  ${AMARELO}Comandos úteis:${RESET}"
    echo -e "  cd ${APP_DIR}"
    echo -e "  make status     # Ver status dos serviços"
    echo -e "  make logs       # Ver logs em tempo real"
    echo -e "  make help       # Ver todos os comandos"
    echo ""
    echo -e "  ${AMARELO}Credenciais:${RESET} cat /root/webscraper_credentials.txt"
    echo ""
}

# ------------------------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ------------------------------------------------------------------------------
main() {
    banner
    verificar_privilegios
    
    # Confirmar execução
    echo -e "${AMARELO}Este script irá configurar o servidor do zero.${RESET}"
    read -p "Continuar? (s/N) " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        info "Execução cancelada pelo usuário."
        exit 0
    fi
    
    echo ""
    INICIO=$(date +%s)
    
    atualizar_sistema
    instalar_docker
    configurar_firewall
    configurar_swap
    criar_usuario_app
    clonar_repositorio
    configurar_env
    subir_stack
    aguardar_servicos
    finalizar
    
    FIM=$(date +%s)
    DURACAO=$((FIM - INICIO))
    
    log "Setup completo em ${DURACAO} segundos!"
    echo ""
    
    # Recarregar grupos do usuário para acessar Docker sem sudo
    warn "NOTA: Faça logout e login novamente para usar Docker sem sudo"
}

main "$@"
