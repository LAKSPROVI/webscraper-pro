"""
proxy.py — Middleware de rotação e gerenciamento de proxies

Gerencia um pool de proxies carregados do Redis com:
- Rotação round-robin entre proxies disponíveis
- Health tracking: marca proxies como falhos em erros HTTP
- Exclusão automática de proxies com taxa de falha > 30%
- Suporte a HTTP, HTTPS e SOCKS5
- Fallback para IP direto se todos os proxies falharem

Os proxies são armazenados no Redis como um SET com a chave 'proxies:pool'.
Formato dos proxies: "http://ip:porta", "https://ip:porta" ou "socks5://ip:porta"
Para proxies autenticados: "http://usuario:senha@ip:porta"
"""

import logging
import random
import time
from collections import defaultdict
from typing import Optional

import redis as redis_lib
from scrapy.http import Request, Response

logger = logging.getLogger(__name__)

# Chaves Redis para o pool de proxies
REDIS_PROXY_POOL_KEY = "proxies:pool"           # SET com todos os proxies
REDIS_PROXY_ACTIVE_KEY = "active_proxies"       # SET legado/worker updater
REDIS_PROXY_ENABLED_KEY = "proxy:enabled"       # STRING bool (1/0)
REDIS_PROXY_FAILURES_KEY = "proxies:failures:"  # HASH prefixo para contagem de falhas
REDIS_PROXY_SUCCESSES_KEY = "proxies:successes:" # HASH prefixo para contagem de sucessos


class ProxyMiddleware:
    """
    Middleware de gerenciamento inteligente de proxies.

    Fluxo de operação:
    1. process_request: seleciona proxy disponível e aplica à requisição
    2. process_response: marca proxy como bem-sucedido ou falho
    3. Proxies com >30% de taxa de falha são removidos automaticamente
    4. Se pool vazio, usa conexão direta como fallback
    """

    def __init__(self, settings):
        self.settings = settings
        self._enabled_default = bool(settings.getbool("PROXY_ENABLED", False))
        self._enabled_cache = self._enabled_default
        self._enabled_cache_at = 0.0
        self._enabled_cache_ttl = 10.0
        # Taxa máxima de falha antes de excluir o proxy (30%)
        self.max_failure_rate = 0.30
        # Mínimo de requisições antes de calcular taxa de falha
        self.min_requests_for_eval = 5

        # Lista local de proxies (cache do Redis para evitar consultas excessivas)
        self._proxy_pool: list[str] = []
        # Índice para round-robin
        self._current_index = 0
        # Contador de requisições por proxy para cálculo de taxa de falha
        self._proxy_failures: dict[str, int] = defaultdict(int)
        self._proxy_successes: dict[str, int] = defaultdict(int)

        # Conecta ao Redis para gerenciamento do pool
        redis_url = settings.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            self._redis = redis_lib.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            logger.info(f"ProxyMiddleware conectado ao Redis: {redis_url}")
            # Carrega proxies do Redis na inicialização
            self._load_proxies_from_redis()
        except Exception as e:
            logger.warning(f"ProxyMiddleware: Redis não disponível ({e}). Usando sem proxy.")
            self._redis = None

    @classmethod
    def from_crawler(cls, crawler):
        """Instancia o middleware a partir das configurações do Scrapy."""
        return cls(crawler.settings)

    def _load_proxies_from_redis(self) -> None:
        """Carrega a lista de proxies do Redis para cache local."""
        if not self._redis:
            return
        try:
            proxies = self._redis.smembers(REDIS_PROXY_ACTIVE_KEY)
            if not proxies:
                proxies = self._redis.smembers(REDIS_PROXY_POOL_KEY)
            self._proxy_pool = list(proxies) if proxies else []
            logger.info(f"Carregados {len(self._proxy_pool)} proxies do Redis")
        except Exception as e:
            logger.error(f"Erro ao carregar proxies do Redis: {e}")
            self._proxy_pool = []

    @staticmethod
    def _coerce_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}

    def _is_proxy_globally_enabled(self) -> bool:
        """Verifica chave global de ativação com cache curto para reduzir I/O."""
        agora = time.time()
        if agora - self._enabled_cache_at < self._enabled_cache_ttl:
            return self._enabled_cache

        enabled = self._enabled_default
        if self._redis:
            try:
                raw = self._redis.get(REDIS_PROXY_ENABLED_KEY)
                if raw is not None:
                    enabled = self._coerce_bool(raw)
            except Exception as exc:
                logger.debug("Falha ao ler toggle global de proxy no Redis: %s", exc)

        self._enabled_cache = enabled
        self._enabled_cache_at = agora
        return enabled

    def _get_next_proxy(self) -> Optional[str]:
        """
        Seleciona o próximo proxy disponível via round-robin.

        Verifica saúde de cada proxy antes de usá-lo.
        Retorna None se não houver proxies disponíveis.
        """
        if not self._proxy_pool:
            # Tenta recarregar do Redis antes de desistir
            self._load_proxies_from_redis()
            if not self._proxy_pool:
                return None

        # Tenta encontrar um proxy saudável
        attempts = len(self._proxy_pool)
        for _ in range(attempts):
            if self._current_index >= len(self._proxy_pool):
                self._current_index = 0

            proxy = self._proxy_pool[self._current_index]
            self._current_index += 1

            # Verifica se o proxy não excedeu a taxa de falha
            if self._is_proxy_healthy(proxy):
                return proxy
            else:
                # Remove proxy não saudável do pool
                logger.warning(f"Removendo proxy não saudável: {proxy[:30]}...")
                self._remove_proxy(proxy)
                # Reajusta o índice após remoção
                self._current_index = max(0, self._current_index - 1)

        logger.warning("Nenhum proxy saudável disponível. Usando conexão direta.")
        return None

    def _is_proxy_healthy(self, proxy: str) -> bool:
        """
        Verifica se o proxy está dentro da taxa de falha aceitável.

        Calcula: taxa_falha = falhas / (falhas + sucessos)
        Retorna True se taxa_falha <= max_failure_rate ou total < min_requests_for_eval.
        """
        failures = self._proxy_failures[proxy]
        successes = self._proxy_successes[proxy]
        total = failures + successes

        # Aguarda mínimo de requisições antes de avaliar
        if total < self.min_requests_for_eval:
            return True

        failure_rate = failures / total
        return failure_rate <= self.max_failure_rate

    def _remove_proxy(self, proxy: str) -> None:
        """Remove proxy do pool local e do Redis."""
        if proxy in self._proxy_pool:
            self._proxy_pool.remove(proxy)

        # Remove também do Redis para persistir a exclusão
        if self._redis:
            try:
                self._redis.srem(REDIS_PROXY_POOL_KEY, proxy)
                self._redis.srem(REDIS_PROXY_ACTIVE_KEY, proxy)
                logger.info(f"Proxy removido do pool Redis: {proxy[:30]}...")
            except Exception as e:
                logger.error(f"Erro ao remover proxy do Redis: {e}")

    def process_request(self, request: Request, spider) -> None:
        """
        Aplica proxy à requisição antes de enviá-la.

        Não aplica proxy se:
        - A spider tem custom_settings desabilitando proxies
        - Não há proxies disponíveis (usa conexão direta)
        """
        # Verifica se a spider quer ignorar proxy
        if request.meta.get("dont_use_proxy", False):
            return

        spider_use_proxy = getattr(spider, "use_proxy", None)
        if spider_use_proxy is False:
            return

        force_proxy = request.meta.get("force_use_proxy")
        if force_proxy is None and spider_use_proxy is None and not self._is_proxy_globally_enabled():
            return
        if force_proxy is False:
            return

        # Recarrega proxies do Redis periodicamente (a cada 100 requests)
        if random.random() < 0.01:  # ~1% das vezes
            self._load_proxies_from_redis()

        proxy = self._get_next_proxy()
        if proxy:
            request.meta["proxy"] = proxy
            # Rastreia qual proxy foi usado (para contabilizar resultado)
            request.meta["proxy_used"] = proxy
            logger.debug(f"Usando proxy {proxy[:30]}... para {request.url[:60]}")
        else:
            logger.debug(f"Sem proxy disponível, usando conexão direta para {request.url[:60]}")

    def process_response(self, request: Request, response: Response, spider) -> Response:
        """
        Contabiliza resultado da requisição para health tracking do proxy.

        - Resposta 200-399: contabiliza como sucesso
        - Resposta 403, 407: marca proxy como falho (bloqueado)
        - Resposta 429: proxy pode estar bloqueado ou rate limited
        - Resposta 5xx: possível problema no proxy ou servidor
        """
        proxy = request.meta.get("proxy_used")
        if not proxy:
            return response

        status = response.status

        if 200 <= status < 400:
            # Sucesso: incrementa contador de sucessos
            self._proxy_successes[proxy] += 1

        elif status in (403, 407):
            # 403: acesso proibido (proxy detectado/bloqueado)
            # 407: autenticação de proxy falhou
            self._proxy_failures[proxy] += 1
            logger.warning(
                f"Proxy possivelmente bloqueado (HTTP {status}): "
                f"{proxy[:30]}... em {request.url[:60]}"
            )

        elif status == 429:
            # Rate limit: incrementa falhas mais suavemente
            self._proxy_failures[proxy] += 1
            logger.info(f"Rate limit (429) via proxy {proxy[:30]}...")

        elif status >= 500:
            # Erro de servidor — pode ser proxy com problema
            self._proxy_failures[proxy] += 1

        # Verifica se o proxy deve ser excluído após esta resposta
        if not self._is_proxy_healthy(proxy):
            logger.warning(
                f"Proxy excedeu taxa de falha ({self.max_failure_rate*100:.0f}%): "
                f"{proxy[:30]}..."
            )
            self._remove_proxy(proxy)

        return response

    def process_exception(self, request: Request, exception, spider):
        """
        Trata exceções de conexão (timeout, recusa de conexão, etc.).

        Marca o proxy como falho para que seja avaliado para exclusão.
        """
        proxy = request.meta.get("proxy_used")
        if proxy:
            self._proxy_failures[proxy] += 1
            logger.warning(
                f"Exceção com proxy {proxy[:30]}...: "
                f"{type(exception).__name__}: {exception}"
            )
