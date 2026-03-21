# =============================================================================
# Dockerfile — API FastAPI do WebScraper Jurídico
# =============================================================================
# Base: Python 3.11-slim (menor footprint que a imagem completa)
# Padrão: multi-stage build para imagem final enxuta
# =============================================================================

# -----------------------------------------------------------------------------
# Estágio 1: Builder — instala dependências
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Metadados da imagem
LABEL maintainer="WebScraper Jurídico"
LABEL description="API FastAPI para o sistema de webscraping jurídico"
LABEL version="1.0.0"

# Variáveis de build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

# Instala dependências de sistema necessárias para compilar pacotes Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Ferramentas de compilação
    build-essential \
    gcc \
    g++ \
    # Dependências para asyncpg (PostgreSQL async)
    libpq-dev \
    # Dependências de criptografia
    libssl-dev \
    libffi-dev \
    # curl para healthcheck
    curl \
    # Limpeza do cache apt
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho para o build
WORKDIR /build

# Copia apenas os arquivos de dependências primeiro (aproveita cache do Docker)
COPY requirements.txt .

# Instala as dependências Python em /install (para copiar no próximo estágio)
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-warn-script-location -r requirements.txt

# -----------------------------------------------------------------------------
# Estágio 2: Runtime — imagem final de produção
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Variáveis de ambiente de runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    # Garante que os pacotes instalados no builder sejam encontrados
    PATH=/install/bin:$PATH

# Instala apenas as dependências de runtime (sem ferramentas de compilação)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Runtime do PostgreSQL (libpq)
    libpq5 \
    # curl para healthcheck no docker-compose
    curl \
    # Timezone data
    tzdata \
    # Limpeza
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    # Configura timezone para Brasília
    && ln -sf /usr/share/zoneinfo/America/Sao_Paulo /etc/localtime \
    && echo "America/Sao_Paulo" > /etc/timezone

# Copia os pacotes Python instalados no builder
COPY --from=builder /install /usr/local

# Cria usuário não-root para segurança
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Diretório principal da aplicação
WORKDIR /app

# Cria diretórios necessários com as permissões corretas
RUN mkdir -p /app/logs /app/uploads /app/temp && \
    chown -R appuser:appgroup /app

# Copia o código da aplicação
# (copiado após as dependências para aproveitar o cache do Docker)
COPY --chown=appuser:appgroup . .

# Muda para o usuário não-root
USER appuser

# Porta exposta pela API
EXPOSE 8000

# Healthcheck interno do container
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando padrão: inicia o servidor Uvicorn com auto-reload em dev
# Em produção, use: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload", \
     "--log-level", "info", \
     "--access-log"]
