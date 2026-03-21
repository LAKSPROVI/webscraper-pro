"""
main.py — Entry point da API FastAPI do WebScraper Jurídico

Configura:
    - Aplicação FastAPI com título, versão e descrição
    - CORS configurado via variável de ambiente API_CORS_ORIGINS
    - Lifecycle: startup (init_db, proxy_updater) e shutdown
    - Todos os roteadores incluídos com prefixos corretos
    - Endpoints de sistema: GET /, GET /health, GET /metrics
    - Middlewares: RequestLoggingMiddleware, PrometheusMiddleware
    - Exception handlers: 404, 422, 500
    - Swagger UI em /docs, ReDoc em /redoc

Uso:
    uvicorn webscraper.api.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from webscraper.database.connection import check_db, close_db, init_db
from webscraper.api.middleware import PrometheusMiddleware, RequestLoggingMiddleware
from webscraper.api.routers import data, jobs, schedule, scrape, spiders

# ---------------------------------------------------------------------------
# Configuração de Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("webscraper.api")

# ---------------------------------------------------------------------------
# Variáveis de Ambiente
# ---------------------------------------------------------------------------

API_VERSION: str = os.getenv("API_VERSION", "v1")
API_ENV: str = os.getenv("API_ENV", "development")
API_DEBUG: bool = os.getenv("API_DEBUG", "false").lower() == "true"
REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Origens CORS — lê da env e divide por vírgula
_cors_origins_raw = os.getenv(
    "API_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8000",
)
CORS_ORIGINS: list[str] = [origin.strip() for origin in _cors_origins_raw.split(",") if origin.strip()]


# ---------------------------------------------------------------------------
# Lifecycle da Aplicação
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Gerencia o ciclo de vida da aplicação FastAPI.

    Startup:
        - Inicializa o banco de dados (cria tabelas se necessário)
        - Registra horário de início da aplicação

    Shutdown:
        - Fecha conexões do banco de dados de forma ordenada
        - Loga o tempo total de execução
    """
    # ── STARTUP ──────────────────────────────────────────────────────────────
    inicio = time.time()
    logger.info("=" * 60)
    logger.info("WebScraper Jurídico API — Iniciando...")
    logger.info("Ambiente: %s | Versão: %s", API_ENV, API_VERSION)
    logger.info("=" * 60)

    # Inicializa o banco de dados
    try:
        await init_db()
        logger.info("✓ Banco de dados inicializado")
    except Exception as exc:
        logger.error("✗ Erro ao inicializar banco de dados: %s", exc)
        # Não encerra a aplicação — pode funcionar sem DB inicialmente

    # Guarda o tempo de início no state da aplicação
    app.state.started_at = datetime.now(tz=timezone.utc)
    app.state.startup_time_ms = (time.time() - inicio) * 1000

    logger.info(
        "✓ API iniciada em %.1fms",
        app.state.startup_time_ms,
    )

    yield  # Aplicação em execução

    # ── SHUTDOWN ─────────────────────────────────────────────────────────────
    logger.info("WebScraper Jurídico API — Encerrando...")

    # Fecha conexões do banco de dados
    try:
        await close_db()
        logger.info("✓ Conexões do banco de dados encerradas")
    except Exception as exc:
        logger.error("✗ Erro ao fechar banco de dados: %s", exc)

    uptime_segundos = (datetime.now(tz=timezone.utc) - app.state.started_at).total_seconds()
    logger.info("✓ API encerrada. Uptime: %.0fs", uptime_segundos)


# ---------------------------------------------------------------------------
# Criação da Aplicação FastAPI
# ---------------------------------------------------------------------------


app = FastAPI(
    title="WebScraper Jurídico API",
    version="1.0.0",
    description="""
## WebScraper Jurídico — API REST

Sistema de web scraping especializado em documentos jurídicos brasileiros.

### Funcionalidades

- 🔍 **Scraping** — Disparo imediato e em lote de coletas de dados
- 📊 **Jobs** — Monitoramento em tempo real via WebSocket
- 🗄️ **Dados** — Busca full-text, exportação JSON/CSV
- 🕷️ **Spiders** — Gerenciamento de configurações de spider
- ⏰ **Agendamentos** — Jobs periódicos com expressão CRON

### Autenticação

Atualmente em desenvolvimento. As futuras versões incluirão autenticação JWT.

### Versionamento

Todos os endpoints estão sob o prefixo `/api/v1/`.

### Monitoramento

- Métricas Prometheus disponíveis em `/metrics`
- Health check em `/health`
- WebSocket de jobs em `/api/v1/ws/jobs`
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    debug=API_DEBUG,
)


# ---------------------------------------------------------------------------
# Middlewares
# ---------------------------------------------------------------------------

# CORS — deve ser adicionado antes dos outros middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

# Logging de requisições (exclui health/metrics para não poluir o log)
app.add_middleware(
    RequestLoggingMiddleware,
    exclude_paths=["/health", "/metrics", "/favicon.ico", "/openapi.json"],
)

# Métricas Prometheus
app.add_middleware(PrometheusMiddleware, app_name="webscraper_api")


# ---------------------------------------------------------------------------
# Exception Handlers
# ---------------------------------------------------------------------------


@app.exception_handler(404)
async def handler_404(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handler para recursos não encontrados (404).
    Retorna resposta padronizada em português.
    """
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "erro": "Recurso não encontrado",
            "detalhes": str(exc.detail) if hasattr(exc, "detail") else f"O recurso '{request.url.path}' não existe.",
            "codigo": 404,
            "path": request.url.path,
        },
    )


@app.exception_handler(RequestValidationError)
async def handler_422(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handler para erros de validação Pydantic (422).
    Formata os erros de validação em português.
    """
    campos_invalidos = []
    for error in exc.errors():
        campo = " → ".join(str(loc) for loc in error["loc"] if loc != "body")
        campos_invalidos.append({
            "campo": campo,
            "mensagem": error["msg"],
            "tipo": error["type"],
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "erro": "Erro de validação nos dados enviados",
            "campos_invalidos": campos_invalidos,
            "codigo": 422,
        },
    )


@app.exception_handler(500)
async def handler_500(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler para erros internos do servidor (500).
    Oculta detalhes técnicos em produção.
    """
    logger.error(
        "Erro interno do servidor: path=%s method=%s error=%s",
        request.url.path,
        request.method,
        exc,
        exc_info=True,
    )

    # Em desenvolvimento, retorna detalhes do erro
    if API_DEBUG:
        detalhe = str(exc)
    else:
        detalhe = "Erro interno do servidor. Nossa equipe foi notificada. Tente novamente em instantes."

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "erro": "Erro interno do servidor",
            "detalhes": detalhe,
            "codigo": 500,
        },
    )


@app.exception_handler(HTTPException)
async def handler_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Handler genérico para HTTPException com formato padronizado.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "erro": exc.detail if isinstance(exc.detail, str) else "Erro na requisição",
            "detalhes": exc.detail if not isinstance(exc.detail, str) else None,
            "codigo": exc.status_code,
        },
    )


# ---------------------------------------------------------------------------
# Inclusão dos Roteadores
# ---------------------------------------------------------------------------

# Router de scraping imediato
app.include_router(scrape.router)

# Router de gerenciamento de jobs
app.include_router(jobs.router)

# Router de consulta de dados coletados
app.include_router(data.router)

# Router de configurações de spiders
app.include_router(spiders.router)

# Router de agendamentos CRON
app.include_router(schedule.router)


# ---------------------------------------------------------------------------
# Endpoints de Sistema
# ---------------------------------------------------------------------------


@app.get(
    "/",
    summary="Informações da API",
    description="Retorna informações gerais sobre a API, versão e endpoints disponíveis.",
    tags=["Sistema"],
)
async def raiz() -> dict[str, Any]:
    """
    Endpoint raiz com informações da API.

    Returns:
        Dict com nome, versão, ambiente e links úteis.
    """
    return {
        "nome": "WebScraper Jurídico API",
        "versao": "1.0.0",
        "ambiente": API_ENV,
        "descricao": "API REST para gerenciamento de scraping jurídico",
        "documentacao": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi_json": "/openapi.json",
        },
        "endpoints_principais": {
            "scraping": "/api/v1/scrape",
            "jobs": "/api/v1/jobs",
            "dados": "/api/v1/data",
            "spiders": "/api/v1/spiders",
            "agendamentos": "/api/v1/schedule",
            "websocket": "/api/v1/ws/jobs",
        },
        "monitoramento": {
            "health": "/health",
            "metrics": "/metrics",
        },
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.get(
    "/health",
    summary="Health check",
    description="""
    Verifica o status de saúde de todos os componentes da aplicação.

    Componentes verificados:
    - **database**: Conectividade com PostgreSQL
    - **redis**: Conectividade com Redis

    Status possíveis: `ok`, `error`, `degraded`
    """,
    tags=["Sistema"],
)
async def health_check() -> JSONResponse:
    """
    Verifica a saúde de todos os componentes da aplicação.

    Executa queries de teste em cada serviço e agrega os resultados.
    O status geral é `ok` somente se todos os componentes estiverem `ok`.

    Returns:
        JSONResponse com status geral e status individual de cada componente.
    """
    inicio = time.perf_counter()

    # Verifica banco de dados
    db_inicio = time.perf_counter()
    db_status = await check_db()
    db_latencia = (time.perf_counter() - db_inicio) * 1000

    # Verifica Redis
    redis_status: dict[str, Any] = {}
    redis_inicio = time.perf_counter()
    try:
        import redis.asyncio as aioredis
        cliente = await aioredis.from_url(REDIS_URL, decode_responses=True)
        await cliente.ping()
        await cliente.aclose()
        redis_status = {"status": "ok", "message": "Redis acessível"}
    except Exception as exc:
        redis_status = {"status": "error", "message": f"Redis inacessível: {str(exc)[:100]}"}
    redis_latencia = (time.perf_counter() - redis_inicio) * 1000

    # Agrega status geral
    todos_ok = db_status.get("status") == "ok" and redis_status.get("status") == "ok"
    status_geral = "ok" if todos_ok else "error"

    # Calcula uptime
    uptime: str = "desconhecido"
    if hasattr(app.state, "started_at"):
        delta = datetime.now(tz=timezone.utc) - app.state.started_at
        total_s = int(delta.total_seconds())
        horas = total_s // 3600
        minutos = (total_s % 3600) // 60
        segundos = total_s % 60
        uptime = f"{horas}h {minutos}min {segundos}s"

    tempo_total_ms = (time.perf_counter() - inicio) * 1000

    response_data = {
        "status": status_geral,
        "versao": "1.0.0",
        "ambiente": API_ENV,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "uptime": uptime,
        "tempo_verificacao_ms": round(tempo_total_ms, 2),
        "componentes": {
            "database": {
                "status": db_status.get("status", "error"),
                "message": db_status.get("message", "Desconhecido"),
                "latency_ms": round(db_latencia, 2),
            },
            "redis": {
                "status": redis_status.get("status", "error"),
                "message": redis_status.get("message", "Desconhecido"),
                "latency_ms": round(redis_latencia, 2),
            },
        },
    }

    # Retorna 200 mesmo com erro para que o load balancer não remova a instância
    # imediatamente (comportamento configurável)
    http_status = status.HTTP_200_OK if todos_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(content=response_data, status_code=http_status)


@app.get(
    "/metrics",
    summary="Métricas Prometheus",
    description="""
    Expõe métricas no formato Prometheus para scraping pelo servidor de métricas.

    Métricas disponíveis:
    - `http_requests_total` — Total de requisições por método/rota/status
    - `http_request_duration_seconds` — Histograma de latência por rota
    - `http_errors_total` — Total de erros por rota
    """,
    tags=["Monitoramento"],
    include_in_schema=False,  # Não aparece no Swagger (é para Prometheus)
)
async def metrics_endpoint() -> Response:
    """
    Endpoint de métricas para o Prometheus.

    Retorna todas as métricas coletadas no formato text/plain do Prometheus.

    Returns:
        Response com métricas no formato Prometheus.
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
