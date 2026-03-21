"""
ratelimit.py — Middleware de controle de taxa por domínio

Implementa rate limiting inteligente usando:
- Token Bucket Algorithm: acumula tokens ao longo do tempo
- Redis como contador centralizado (suporta múltiplos workers)
- Circuit Breaker: pausa automática após erros consecutivos
- Respeito ao header Retry-After em respostas 429

Configuração por spider via custom_settings ou settings.py:
```python
RATE_LIMITS = {
    "meu_spider": {
        "exemplo.com": {"requests_per_second": 2, "burst": 5}
    }
}
```
Padrão: 2 req/s com burst de 10.
"""

import logging
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse

import redis as redis_lib
from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response

logger = logging.getLogger(__name__)

# Configuração padrão de rate limit
DEFAULT_RATE_LIMIT = {
    "requests_per_second": 2.0,  # Tokens por segundo adicionados ao bucket
    "burst": 10,                  # Capacidade máxima do bucket (burst máximo)
}

# Prefixo das chaves Redis para controle de rate limit
REDIS_RATE_KEY = "ratelimit:tokens:"     # Hash com tokens disponíveis
REDIS_CIRCUIT_KEY = "ratelimit:circuit:" # Hash com estado do circuit breaker
REDIS_ERRORS_KEY = "ratelimit:errors:"  # Hash com contador de erros consecutivos


class RateLimitMiddleware:
    """
    Middleware de rate limiting com Token Bucket e Circuit Breaker.

    Token Bucket Algorithm:
    - Cada domínio tem um "bucket" de tokens
    - Tokens são adicionados ao bucket em ritmo constante (req/s)
    - Cada request consome 1 token
    - Se sem tokens: aguarda até ter token disponível
    - Burst: capacidade máxima do bucket (permite picos momentâneos)

    Circuit Breaker:
    - Após 5 erros consecutivos (4xx/5xx): abre o circuito
    - Com circuito aberto: pausa 60 segundos no domínio
    - Após pausa: reinicia contagem de erros (tenta novamente)
    """

    # Número de erros consecutivos para abrir o circuit breaker
    CIRCUIT_BREAKER_THRESHOLD = 5
    # Tempo de pausa quando o circuit breaker é ativado (segundos)
    CIRCUIT_BREAKER_PAUSE = 60.0

    def __init__(self, settings):
        self.settings = settings

        # Configura rate limits por spider (carregado das settings)
        self._rate_limits: dict = settings.get("RATE_LIMITS", {})

        # Estado local do token bucket por domínio
        # {domínio: {"tokens": float, "last_refill": float}}
        self._buckets: dict[str, dict] = defaultdict(lambda: {
            "tokens": DEFAULT_RATE_LIMIT["burst"],
            "last_refill": time.time(),
        })

        # Estado do circuit breaker por domínio
        # {domínio: {"errors": int, "open_until": float}}
        self._circuit_breaker: dict[str, dict] = defaultdict(lambda: {
            "errors": 0,
            "open_until": 0.0,
        })

        # Rastreia timestamps de Retry-After por domínio
        self._retry_after: dict[str, float] = {}

        # Conecta ao Redis para controle centralizado
        redis_url = settings.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            self._redis = redis_lib.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            logger.info("RateLimitMiddleware: Redis conectado")
        except Exception as e:
            logger.warning(
                f"RateLimitMiddleware: Redis não disponível ({e}). "
                "Usando controle local (não funciona com múltiplos workers)."
            )
            self._redis = None

    @classmethod
    def from_crawler(cls, crawler):
        """Instancia o middleware a partir das configurações do Scrapy."""
        return cls(crawler.settings)

    def process_request(self, request: Request, spider) -> None:
        """
        Verifica rate limit e circuit breaker antes de processar a request.

        Se o circuit breaker estiver aberto para o domínio:
        - Loga aviso e adiciona delay via request.meta

        Se sem tokens disponíveis:
        - Aguarda até ter token (blocking sleep)
        """
        domain = urlparse(request.url).netloc

        # ── Verifica Retry-After (de resposta 429 anterior) ───────────────
        retry_after = self._retry_after.get(domain)
        if retry_after and time.time() < retry_after:
            wait_time = retry_after - time.time()
            logger.info(f"Aguardando Retry-After de {wait_time:.1f}s para {domain}")
            time.sleep(wait_time)
            del self._retry_after[domain]

        # ── Verifica circuit breaker ───────────────────────────────────────
        circuit = self._circuit_breaker[domain]
        if time.time() < circuit["open_until"]:
            wait_remaining = circuit["open_until"] - time.time()
            logger.warning(
                f"Circuit breaker ABERTO para {domain}. "
                f"Aguardando {wait_remaining:.1f}s..."
            )
            time.sleep(wait_remaining)
            # Reinicia contador de erros após a pausa
            circuit["errors"] = 0
            circuit["open_until"] = 0.0

        # ── Token Bucket: aguarda token disponível ────────────────────────
        wait_time = self._consume_token(domain, spider)
        if wait_time > 0:
            logger.debug(
                f"Rate limit para {domain}: aguardando {wait_time:.2f}s "
                f"(fila de tokens)"
            )
            time.sleep(wait_time)

    def process_response(self, request: Request, response: Response, spider) -> Response:
        """
        Atualiza estado do circuit breaker baseado na resposta.

        Erros 4xx/5xx incrementam contador. Sucesso reseta o contador.
        Respeita header Retry-After em respostas 429.
        """
        domain = urlparse(request.url).netloc
        status = response.status

        # Resposta de sucesso reseta o circuit breaker
        if 200 <= status < 400:
            circuit = self._circuit_breaker[domain]
            if circuit["errors"] > 0:
                logger.debug(f"Circuit breaker resetado para {domain} após sucesso")
                circuit["errors"] = 0

        elif status == 429:
            # Too Many Requests: extrai Retry-After se presente
            retry_after_header = response.headers.get("Retry-After", b"").decode()
            if retry_after_header:
                try:
                    wait_secs = int(retry_after_header)
                    self._retry_after[domain] = time.time() + wait_secs
                    logger.warning(
                        f"429 em {domain}: Retry-After={wait_secs}s configurado"
                    )
                except ValueError:
                    # Pode ser uma data HTTP ao invés de número de segundos
                    pass
            else:
                # Sem Retry-After: usa 30s como padrão conservador
                self._retry_after[domain] = time.time() + 30
                logger.warning(f"429 em {domain}: aguardando 30s (padrão)")

            # Incrementa contador do circuit breaker
            self._increment_error(domain)

        elif status >= 400:
            # Outros erros HTTP
            self._increment_error(domain)

        return response

    def process_exception(self, request: Request, exception, spider):
        """Trata exceções de rede como erros para o circuit breaker."""
        domain = urlparse(request.url).netloc
        self._increment_error(domain)

    def _consume_token(self, domain: str, spider) -> float:
        """
        Consome um token do bucket e retorna o tempo de espera.

        Implementa Token Bucket Algorithm:
        1. Calcula tokens acumulados desde último refill
        2. Adiciona ao bucket (limitado ao burst máximo)
        3. Se há token disponível: consome e retorna 0
        4. Se sem token: retorna tempo de espera até próximo token

        Retorna:
            float: segundos a aguardar (0 se token disponível imediatamente)
        """
        # Obtém configuração de rate limit para este domínio/spider
        rate_config = self._get_rate_config(domain, spider)
        rate = rate_config["requests_per_second"]
        burst = rate_config["burst"]

        bucket = self._buckets[domain]
        now = time.time()

        # Calcula tokens acumulados desde último refill
        elapsed = now - bucket["last_refill"]
        new_tokens = elapsed * rate
        bucket["tokens"] = min(burst, bucket["tokens"] + new_tokens)
        bucket["last_refill"] = now

        if bucket["tokens"] >= 1.0:
            # Token disponível: consome e procede sem espera
            bucket["tokens"] -= 1.0
            return 0.0
        else:
            # Sem token: calcula tempo até próximo token
            wait_time = (1.0 - bucket["tokens"]) / rate
            bucket["tokens"] = 0.0  # Zera tokens (serão recarregados após espera)
            return wait_time

    def _increment_error(self, domain: str) -> None:
        """
        Incrementa contador de erros do circuit breaker.

        Se atingir o threshold, abre o circuito por CIRCUIT_BREAKER_PAUSE segundos.
        """
        circuit = self._circuit_breaker[domain]
        circuit["errors"] += 1

        if circuit["errors"] >= self.CIRCUIT_BREAKER_THRESHOLD:
            circuit["open_until"] = time.time() + self.CIRCUIT_BREAKER_PAUSE
            logger.warning(
                f"Circuit breaker ATIVADO para {domain}: "
                f"{circuit['errors']} erros consecutivos. "
                f"Pausando por {self.CIRCUIT_BREAKER_PAUSE}s."
            )

    def _get_rate_config(self, domain: str, spider) -> dict:
        """
        Obtém configuração de rate limit para o domínio/spider.

        Prioridade:
        1. custom_settings da spider para o domínio específico
        2. Configuração geral para o domínio nas settings
        3. Configuração padrão (DEFAULT_RATE_LIMIT)
        """
        spider_name = getattr(spider, "name", "")

        # Verifica configuração específica da spider
        spider_limits = self._rate_limits.get(spider_name, {})
        domain_config = spider_limits.get(domain)
        if domain_config:
            return {**DEFAULT_RATE_LIMIT, **domain_config}

        # Verifica configuração global para o domínio
        global_limits = self._rate_limits.get("*", {})
        domain_config = global_limits.get(domain)
        if domain_config:
            return {**DEFAULT_RATE_LIMIT, **domain_config}

        return DEFAULT_RATE_LIMIT
