"""
middleware.py — Middlewares customizados para a API do WebScraper Jurídico

Implementa:
    - RequestLoggingMiddleware: Loga método, path, status e tempo de resposta
    - PrometheusMiddleware: Incrementa métricas Prometheus por rota/método/status
"""

from __future__ import annotations

import logging
import time
from typing import Callable

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import ASGIApp

logger = logging.getLogger("webscraper.api.access")

# ---------------------------------------------------------------------------
# Métricas Prometheus
# ---------------------------------------------------------------------------

# Contador de requisições HTTP por método, rota e status
http_requests_total = Counter(
    "http_requests_total",
    "Total de requisições HTTP recebidas",
    labelnames=["method", "path", "status"],
)

# Histograma de duração das requisições em segundos
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Duração das requisições HTTP em segundos",
    labelnames=["method", "path"],
    # Buckets: 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Contador de erros HTTP (status >= 400)
http_errors_total = Counter(
    "http_errors_total",
    "Total de respostas com erro HTTP",
    labelnames=["method", "path", "status"],
)

# Contador de requisições ativas em andamento
http_requests_in_progress = Counter(
    "http_requests_in_progress_total",
    "Total de requisições processadas (proxy para gauge)",
    labelnames=["method", "path"],
)


# ---------------------------------------------------------------------------
# Middleware: Logging de Requisições
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware que loga informações de cada requisição HTTP.

    Para cada requisição, registra:
        - Método HTTP (GET, POST, etc.)
        - Path da requisição
        - Status code da resposta
        - Tempo de processamento em milissegundos
        - IP do cliente

    Nível de log:
        - INFO para respostas 2xx e 3xx
        - WARNING para respostas 4xx
        - ERROR para respostas 5xx
    """

    def __init__(self, app: ASGIApp, *, exclude_paths: list[str] | None = None) -> None:
        """
        Inicializa o middleware.

        Args:
            app: Aplicação ASGI subjacente.
            exclude_paths: Paths a excluir do log (ex: /health, /metrics).
        """
        super().__init__(app)
        # Paths que não serão logados (reduz ruído em health checks)
        self.exclude_paths: list[str] = exclude_paths or ["/health", "/metrics", "/favicon.ico"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Intercepta a requisição, mede o tempo e loga o resultado.

        Args:
            request: Objeto Request do Starlette.
            call_next: Função para chamar o próximo middleware/endpoint.

        Returns:
            Response da aplicação.
        """
        path = request.url.path

        # Ignora paths excluídos (health checks, metrics, etc.)
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            return await call_next(request)

        # Captura IP do cliente (considera proxies reversos via X-Forwarded-For)
        client_ip = request.headers.get("x-forwarded-for", "")
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"
        else:
            # Pega o primeiro IP da cadeia de proxies
            client_ip = client_ip.split(",")[0].strip()

        # Marca o início da requisição
        start_time = time.perf_counter()

        # Processa a requisição
        response: Response = await call_next(request)

        # Calcula o tempo de processamento em ms
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        status_code = response.status_code
        method = request.method

        # Formata a mensagem de log
        log_msg = (
            f"{method} {path} → {status_code} "
            f"({elapsed_ms:.1f}ms) "
            f"[{client_ip}]"
        )

        # Escolhe o nível de log baseado no status code
        if status_code < 400:
            logger.info(log_msg)
        elif status_code < 500:
            logger.warning(log_msg)
        else:
            logger.error(log_msg)

        return response


# ---------------------------------------------------------------------------
# Middleware: Métricas Prometheus
# ---------------------------------------------------------------------------


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Middleware que coleta métricas Prometheus para cada requisição.

    Coleta:
        - http_requests_total: contador por método/path/status
        - http_request_duration_seconds: histograma de latência
        - http_errors_total: contador de erros (status >= 400)

    As rotas são normalizadas para evitar cardinalidade excessiva
    (ex: /api/v1/jobs/123 → /api/v1/jobs/{job_id}).
    """

    def __init__(self, app: ASGIApp, *, app_name: str = "webscraper_api") -> None:
        """
        Inicializa o middleware Prometheus.

        Args:
            app: Aplicação ASGI subjacente.
            app_name: Nome da aplicação para prefixo de métricas.
        """
        super().__init__(app)
        self.app_name = app_name
        # Paths a excluir das métricas (reduz cardinalidade)
        self.exclude_paths: list[str] = ["/metrics", "/favicon.ico", "/docs", "/redoc", "/openapi.json"]

    def _normalizar_path(self, request: Request) -> str:
        """
        Normaliza o path para reduzir cardinalidade das métricas.

        Converte IDs numéricos em placeholders:
            /api/v1/jobs/123 → /api/v1/jobs/{id}
            /api/v1/data/item/456 → /api/v1/data/item/{id}

        Args:
            request: Requisição com informações de roteamento.

        Returns:
            Path normalizado para uso como label de métrica.
        """
        path = request.url.path

        # Tenta obter a rota correspondente do router FastAPI
        # para usar o template de path com parâmetros nomeados
        if hasattr(request, "app"):
            for route in request.app.routes:
                match, scope = route.matches({"type": "http", "path": path, "method": request.method})
                if match == Match.FULL:
                    return route.path  # type: ignore[attr-defined]

        # Fallback: substitui segmentos numéricos por {id}
        import re
        path_normalizado = re.sub(r"/\d+", "/{id}", path)
        return path_normalizado

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Intercepta a requisição e atualiza as métricas Prometheus.

        Args:
            request: Objeto Request do Starlette.
            call_next: Função para chamar o próximo middleware/endpoint.

        Returns:
            Response da aplicação.
        """
        path = request.url.path

        # Ignora paths excluídos das métricas
        if any(path.startswith(excluded) for excluded in self.exclude_paths):
            return await call_next(request)

        method = request.method
        path_normalizado = self._normalizar_path(request)

        # Marca início para medir duração
        start_time = time.perf_counter()

        # Incrementa contador de requisições em andamento
        http_requests_in_progress.labels(method=method, path=path_normalizado).inc()

        # Processa a requisição
        response: Response = await call_next(request)

        # Calcula duração em segundos
        duration = time.perf_counter() - start_time
        status_code = str(response.status_code)

        # Atualiza métricas
        http_requests_total.labels(
            method=method,
            path=path_normalizado,
            status=status_code,
        ).inc()

        http_request_duration_seconds.labels(
            method=method,
            path=path_normalizado,
        ).observe(duration)

        # Incrementa contador de erros se status >= 400
        if response.status_code >= 400:
            http_errors_total.labels(
                method=method,
                path=path_normalizado,
                status=status_code,
            ).inc()

        return response
