#!/bin/bash
# ============================================================
# 🕷️ WebScraper Pro — Setup automático do Codespace
# Executado automaticamente após criar o container
# ============================================================

set -e

echo ""
echo "═══════════════════════════════════════════════"
echo "  🕷️  WebScraper Pro — Configurando ambiente..."
echo "═══════════════════════════════════════════════"
echo ""

# ── 1. Configurar .env ──────────────────────────────────────
echo "📋 Configurando variáveis de ambiente..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    # Gera senhas aleatórias para o ambiente de desenvolvimento
    DB_PASS=$(openssl rand -base64 16 | tr -d "=+/" | cut -c1-16)
    REDIS_PASS=$(openssl rand -base64 12 | tr -d "=+/" | cut -c1-12)
    SECRET=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
    GRAFANA_PASS=$(openssl rand -base64 12 | tr -d "=+/" | cut -c1-12)
    PGADMIN_PASS=$(openssl rand -base64 12 | tr -d "=+/" | cut -c1-12)
    
    sed -i "s/scraper_pass_change_me/${DB_PASS}/g" .env
    sed -i "s/change_me_to_random_secret/${SECRET}/g" .env
    sed -i "s/admin_change_me/${GRAFANA_PASS}/g" .env
    sed -i "s/pgadmin_change_me/${PGADMIN_PASS}/g" .env
    
    echo "✅ .env criado com senhas geradas automaticamente"
else
    echo "✅ .env já existe"
fi

# ── 2. Instalar dependências Python (API) ───────────────────
echo ""
echo "🐍 Instalando dependências Python da API..."
pip install --upgrade pip --quiet
pip install -r api/requirements.txt --quiet 2>&1 | tail -5
echo "✅ Dependências API instaladas"

# ── 3. Instalar dependências Python (Scraper) ───────────────
echo ""
echo "🦔 Instalando dependências do Scrapy..."
pip install -r scraper/requirements.txt --quiet 2>&1 | tail -5
echo "✅ Dependências Scrapy instaladas"

# ── 4. Instalar dependências Python (Worker) ────────────────
echo ""
echo "⚙️ Instalando dependências do Worker Celery..."
pip install -r worker/requirements.txt --quiet 2>&1 | tail -5
echo "✅ Dependências Worker instaladas"

# ── 5. Instalar dependências do frontend ────────────────────
echo ""
echo "⚛️ Instalando dependências do Frontend React..."
if command -v npm &>/dev/null; then
    cd frontend
    npm install --silent 2>&1 | tail -3
    cd ..
    echo "✅ Frontend: npm install concluído"
else
    echo "⚠️ npm não encontrado, pulando frontend por agora"
fi

# ── 6. Instalar Playwright ──────────────────────────────────
echo ""
echo "🎭 Instalando Playwright Chromium..."
python -m playwright install chromium --quiet 2>&1 | tail -3
python -m playwright install-deps chromium --quiet 2>&1 | tail -3
echo "✅ Playwright Chromium instalado"

# ── 7. Subir stack Docker ───────────────────────────────────
echo ""
echo "🐳 Subindo stack Docker (PostgreSQL, Redis, API, Worker...)..."
docker compose up -d --build 2>&1 | tail -20

echo ""
echo "⏳ Aguardando serviços ficarem saudáveis (30s)..."
sleep 30

# ── 8. Rodar migrações do banco ─────────────────────────────
echo ""
echo "🗄️ Rodando migrações do banco de dados..."
docker compose exec -T scraper-api python -m alembic -c /app/database/alembic.ini upgrade head 2>&1 || echo "⚠️ Migrações serão rodadas quando API iniciar"

# ── 9. Verificar saúde dos serviços ─────────────────────────
echo ""
echo "🔍 Verificando saúde dos serviços..."
sleep 10

check_service() {
    local name=$1
    local url=$2
    if curl -sf "$url" > /dev/null 2>&1; then
        echo "  ✅ $name — OK"
    else
        echo "  ⚠️ $name — aguardando..."
    fi
}

check_service "FastAPI"   "http://localhost:8000/health"
check_service "Flower"    "http://localhost:5555"
check_service "Grafana"   "http://localhost:3000"
check_service "PgAdmin"   "http://localhost:5050"

# ── 10. Mensagem final ──────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
echo "  ✅ WebScraper Pro — Ambiente pronto!"
echo "═══════════════════════════════════════════════"
echo ""
echo "  📍 Acesse as URLs na aba PORTS do VS Code:"
echo ""
echo "  🚀 API + Swagger:    http://localhost:8000/docs"
echo "  🎨 Frontend:         http://localhost:3000"
echo "  🌸 Flower (Celery):  http://localhost:5555"
echo "  📊 Grafana:          http://localhost:3000 (admin)"
echo "  🔧 PgAdmin:          http://localhost:5050"
echo "  📊 Prometheus:       http://localhost:9090"
echo ""
echo "  🛠️  Comandos úteis:"
echo "     make status       — ver todos os serviços"
echo "     make logs         — ver logs em tempo real"
echo "     make scrape URL=https://quotes.toscrape.com"
echo ""
echo "═══════════════════════════════════════════════"
