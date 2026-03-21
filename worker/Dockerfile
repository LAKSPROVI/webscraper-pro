# =============================================================================
# Dockerfile — Worker Celery com Playwright do WebScraper Jurídico
# =============================================================================
# Base: Python 3.11-slim
# Inclui: Playwright + Chromium para scraping com JavaScript
# ATENÇÃO: Esta imagem é maior que a da API devido ao browser Chromium (~600MB)
# =============================================================================

# -----------------------------------------------------------------------------
# Estágio 1: Builder — instala dependências Python
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

LABEL maintainer="WebScraper Jurídico"
LABEL description="Worker Celery com Playwright para scraping assíncrono"
LABEL version="1.0.0"

# Variáveis de build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

# Instala dependências de compilação
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copia requirements e instala (cache eficiente)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-warn-script-location -r requirements.txt

# -----------------------------------------------------------------------------
# Estágio 2: Runtime com Playwright + Chromium
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Variáveis de ambiente críticas para o Playwright e Celery
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH=/install/bin:$PATH \
    # Diretório de instalação dos browsers do Playwright
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    # Desabilita telemetria do Playwright
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=0 \
    # Força modo headless (sem display)
    DISPLAY=""

# Instala dependências de sistema necessárias para o Chromium
# Lista baseada nas dependências oficiais do Playwright para Chromium no Debian
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Dependências runtime
    libpq5 \
    curl \
    wget \
    tzdata \
    # Dependências do Chromium/Playwright
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libexpat1 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxkbcommon0 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    # Fontes para renderização correta de páginas
    fonts-liberation \
    fonts-noto-color-emoji \
    # Suporte a alguns sites com fontes especiais
    fonts-freefont-ttf \
    # Certs SSL
    ca-certificates \
    # Limpeza
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    # Configura timezone para Brasília
    && ln -sf /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime \
    && echo "America/Sao_Paulo" > /etc/timezone

# Copia pacotes Python do builder
COPY --from=builder /install /usr/local

# Cria usuário não-root
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Diretório principal
WORKDIR /app

# Cria diretórios necessários
RUN mkdir -p \
    /app/logs \
    /app/temp \
    /app/downloads \
    /app/celerybeat \
    /ms-playwright \
    && chown -R appuser:appgroup /app /ms-playwright

# Copia o código da aplicação
COPY --chown=appuser:appgroup . .

# Instala o Playwright e os browsers como usuário (melhor prática de segurança)
# O Chromium é instalado em /ms-playwright
USER appuser

# Instala o Playwright e baixa o Chromium
# Isso acontece durante o build (não em runtime) para evitar atrasos
RUN playwright install chromium && \
    playwright install-deps chromium 2>/dev/null || true

# Verifica se o Playwright está funcionando
RUN python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"

# Porta do Flower (quando este container roda como flower)
EXPOSE 5555

# Healthcheck para o worker Celery
# Usa 'celery inspect ping' para verificar se o worker está respondendo
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
    CMD celery -A app.celery_app inspect ping -d "celery@$HOSTNAME" || exit 1

# Comando padrão: inicia o worker Celery
# Pode ser sobrescrito no docker-compose para beat ou flower
CMD ["celery", "-A", "app.celery_app", "worker", \
     "--loglevel=info", \
     "--concurrency=4", \
     "--queues=default,scraping,high_priority", \
     "--max-tasks-per-child=100"]
