"""
dedup.py — Pipeline de deduplicação de itens via SHA-256

Evita inserção de itens duplicados no banco de dados usando:
- Hash SHA-256 do conteúdo (URL + título + content) como fingerprint único
- Redis SET para armazenar hashes já processados
- Log detalhado de duplicatas por job_id

O algoritmo simula um Bloom Filter usando o Redis SET nativo,
que oferece O(1) de lookup com custo de memória controlado.

Chaves Redis:
- dedup:{job_id} — SET de hashes do job atual (TTL: 24h)
- dedup:global — SET de hashes históricos (sem TTL, crescimento controlado)
"""

import hashlib
import json
import logging
from typing import Optional

import redis as redis_lib
from scrapy.exceptions import DropItem

logger = logging.getLogger(__name__)

# TTL para hashes de jobs específicos (24 horas em segundos)
JOB_HASH_TTL = 86400

# Prefixo das chaves Redis para deduplicação
REDIS_DEDUP_KEY = "dedup:"
REDIS_GLOBAL_DEDUP_KEY = "dedup:global"


class DuplicateFilterPipeline:
    """
    Pipeline que filtra itens duplicados via hashing SHA-256.

    Para cada item recebido:
    1. Calcula SHA-256 dos campos chave (url + título + content)
    2. Verifica no Redis se o hash já existe
    3. Se duplicado: descarta o item com DropItem
    4. Se novo: registra no Redis e deixa passar para próxima pipeline

    Funciona com Redis para suportar múltiplos workers Scrapy simultâneos
    (importante para ambientes com Celery).
    """

    def __init__(self, settings):
        self.settings = settings
        # Cache local de hashes do job atual (evita consultas Redis excessivas)
        self._local_cache: set[str] = set()
        # Contadores para log
        self._duplicates_by_job: dict[str, int] = {}
        self._total_processed = 0

        # Conecta ao Redis
        redis_url = settings.get("REDIS_URL", "redis://localhost:6379/0")
        try:
            self._redis = redis_lib.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            logger.info("DuplicateFilterPipeline: Redis conectado")
        except Exception as e:
            logger.warning(
                f"DuplicateFilterPipeline: Redis não disponível ({e}). "
                "Usando cache em memória (não persiste entre runs)."
            )
            self._redis = None

    @classmethod
    def from_crawler(cls, crawler):
        """Instancia o pipeline a partir das configurações do Scrapy."""
        return cls(crawler.settings)

    def open_spider(self, spider) -> None:
        """Inicializa o pipeline quando o spider começa."""
        logger.info(f"DuplicateFilterPipeline iniciado para spider: {spider.name}")

    def close_spider(self, spider) -> None:
        """Loga estatísticas de duplicatas ao finalizar o spider."""
        total_dupes = sum(self._duplicates_by_job.values())
        logger.info(
            f"DuplicateFilterPipeline finalizado: "
            f"{self._total_processed} itens processados, "
            f"{total_dupes} duplicatas descartadas"
        )
        for job_id, count in self._duplicates_by_job.items():
            if count > 0:
                logger.info(f"  Job {job_id}: {count} duplicatas")

    def process_item(self, item, spider):
        """
        Verifica se o item é duplicado e o descarta se for.

        Calcula o hash usando:
        - URL do item (campo mais determinístico)
        - Título (diferencia variações da mesma URL)
        - Primeiros 1000 chars do content (captura mudanças de conteúdo)

        Raises:
            DropItem: se o item for identificado como duplicado
        """
        self._total_processed += 1

        # Calcula fingerprint SHA-256 do item
        content_hash = self._calculate_hash(item)

        # Obtém job_id para log segmentado
        job_id = str(item.get("job_id") or "unknown")

        # ── Verifica cache local primeiro (mais rápido) ───────────────────
        if content_hash in self._local_cache:
            self._duplicates_by_job[job_id] = (
                self._duplicates_by_job.get(job_id, 0) + 1
            )
            raise DropItem(
                f"Item duplicado (cache local): {item.get('url', 'unknown url')}"
            )

        # ── Verifica no Redis (para múltiplos workers) ────────────────────
        if self._redis:
            if self._is_duplicate_in_redis(content_hash, job_id):
                self._local_cache.add(content_hash)  # Adiciona ao cache local
                self._duplicates_by_job[job_id] = (
                    self._duplicates_by_job.get(job_id, 0) + 1
                )
                raise DropItem(
                    f"Item duplicado (Redis): {item.get('url', 'unknown url')}"
                )

            # Item novo: registra no Redis
            self._register_in_redis(content_hash, job_id)

        # Adiciona ao cache local para verificações futuras
        self._local_cache.add(content_hash)
        logger.debug(
            f"Item aceito (hash: {content_hash[:8]}...): "
            f"{item.get('url', '')[:60]}"
        )

        return item

    def _calculate_hash(self, item) -> str:
        """
        Calcula SHA-256 dos campos chave do item.

        Usa URL + título + início do content para o fingerprint,
        garantindo que conteúdo idêntico de URLs diferentes seja
        tratado como duplicata.
        """
        # Constrói string determinística para hash
        url = str(item.get("url") or "")
        title = str(item.get("title") or "")
        content = str(item.get("content") or "")[:1000]

        # Serializa como JSON para garantir determinismo
        content_str = json.dumps(
            {"url": url, "title": title, "content": content},
            sort_keys=True,
            ensure_ascii=False,
        )

        return hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    def _is_duplicate_in_redis(self, content_hash: str, job_id: str) -> bool:
        """
        Verifica se o hash existe no Redis (job específico ou global).

        Verifica em dois lugares:
        1. Conjunto do job atual (mais recente)
        2. Conjunto global histórico
        """
        try:
            # Verifica no conjunto do job atual
            job_key = f"{REDIS_DEDUP_KEY}{job_id}"
            if self._redis.sismember(job_key, content_hash):
                return True

            # Verifica no conjunto global
            if self._redis.sismember(REDIS_GLOBAL_DEDUP_KEY, content_hash):
                return True

            return False
        except Exception as e:
            logger.error(f"Erro ao verificar duplicata no Redis: {e}")
            return False  # Em caso de erro, permite o item passar

    def _register_in_redis(self, content_hash: str, job_id: str) -> None:
        """
        Registra hash no Redis para deduplicação futura.

        Armazena em:
        - Conjunto específico do job (com TTL de 24h)
        - Conjunto global (sem TTL)
        """
        try:
            # Registra no conjunto do job com TTL
            job_key = f"{REDIS_DEDUP_KEY}{job_id}"
            pipe = self._redis.pipeline()
            pipe.sadd(job_key, content_hash)
            pipe.expire(job_key, JOB_HASH_TTL)
            # Registra no conjunto global
            pipe.sadd(REDIS_GLOBAL_DEDUP_KEY, content_hash)
            pipe.execute()
        except Exception as e:
            logger.error(f"Erro ao registrar hash no Redis: {e}")
