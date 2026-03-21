"""
events.py — Publisher de eventos Redis para o WebScraper Jurídico

Publica eventos de ciclo de vida dos jobs nos canais:
  - job_events:{job_id}  → eventos específicos do job
  - job_events:all       → stream global de eventos (para monitoring)

Formato do evento:
  {
    "job_id": 123,
    "event": "job_started",
    "timestamp": "2024-01-01T10:00:00.000Z",
    "url": "https://...",
    ...dados_extras
  }
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração da conexão Redis
# ---------------------------------------------------------------------------

REDIS_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")


class EventPublisher:
    """
    Publica eventos de jobs no Redis via Pub/Sub.

    Uso:
        publisher = EventPublisher()
        publisher.job_started(job_id=42, url="https://example.com")
        publisher.job_done(job_id=42, items_count=150)
    """

    def __init__(self, redis_url: str = REDIS_URL) -> None:
        """
        Inicializa o publisher com uma conexão Redis.

        Args:
            redis_url: URL de conexão Redis (padrão: variável de ambiente)
        """
        self._redis_url = redis_url
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        """Retorna cliente Redis, criando conexão lazy se necessário."""
        if self._client is None:
            self._client = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )
        return self._client

    def publish_job_event(
        self,
        job_id: int,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """
        Publica um evento de job nos canais Redis.

        Publica em dois canais:
          1. 'job_events:{job_id}' — específico do job
          2. 'job_events:all'      — stream global

        Args:
            job_id:     ID do job relacionado ao evento
            event_type: Tipo do evento (ex: 'started', 'progress', 'done', 'failed')
            data:       Dados adicionais do evento (opcional)
        """
        payload: dict[str, Any] = {
            "job_id": job_id,
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if data:
            payload.update(data)

        message = json.dumps(payload, ensure_ascii=False, default=str)

        try:
            # Publica no canal específico do job
            canal_especifico = f"job_events:{job_id}"
            self.client.publish(canal_especifico, message)

            # Publica no canal global (broadcast)
            self.client.publish("job_events:all", message)

            logger.debug(
                "Evento publicado: job_id=%s, event=%s, canais=[%s, job_events:all]",
                job_id,
                event_type,
                canal_especifico,
            )

        except redis.RedisError as exc:
            # Falha no Redis não deve interromper o worker
            logger.warning(
                "Falha ao publicar evento Redis: job_id=%s, event=%s, erro=%s",
                job_id,
                event_type,
                exc,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Métodos semânticos para cada tipo de evento
    # ──────────────────────────────────────────────────────────────────────────

    def job_created(self, job_id: int, url: str, spider_type: str | None = None) -> None:
        """
        Evento: job criado e enfileirado para execução.

        Args:
            job_id:      ID do job recém-criado
            url:         URL alvo do scraping
            spider_type: Tipo do spider a ser utilizado
        """
        self.publish_job_event(
            job_id=job_id,
            event_type="job_created",
            data={"url": url, "spider_type": spider_type, "status": "pending"},
        )

    def job_started(self, job_id: int, url: str, worker_id: str | None = None) -> None:
        """
        Evento: worker iniciou a execução do job.

        Args:
            job_id:    ID do job em execução
            url:       URL sendo processada
            worker_id: Identificador do worker Celery (opcional)
        """
        self.publish_job_event(
            job_id=job_id,
            event_type="job_started",
            data={"url": url, "status": "running", "worker_id": worker_id},
        )

    def job_progress(
        self,
        job_id: int,
        items_collected: int,
        current_url: str | None = None,
        pages_visited: int | None = None,
    ) -> None:
        """
        Evento: progresso periódico durante a execução do job.

        Args:
            job_id:          ID do job em execução
            items_collected: Quantidade de itens coletados até agora
            current_url:     URL sendo processada no momento (opcional)
            pages_visited:   Número de páginas visitadas até agora (opcional)
        """
        data: dict[str, Any] = {"items_collected": items_collected, "status": "running"}
        if current_url:
            data["current_url"] = current_url
        if pages_visited is not None:
            data["pages_visited"] = pages_visited

        self.publish_job_event(
            job_id=job_id,
            event_type="job_progress",
            data=data,
        )

    def job_done(
        self,
        job_id: int,
        items_count: int,
        duration_seconds: float | None = None,
    ) -> None:
        """
        Evento: job concluído com sucesso.

        Args:
            job_id:           ID do job concluído
            items_count:      Total de itens coletados
            duration_seconds: Duração total em segundos (opcional)
        """
        data: dict[str, Any] = {"items_count": items_count, "status": "done"}
        if duration_seconds is not None:
            data["duration_seconds"] = round(duration_seconds, 2)

        self.publish_job_event(
            job_id=job_id,
            event_type="job_done",
            data=data,
        )

    def job_failed(
        self,
        job_id: int,
        error_msg: str,
        error_type: str | None = None,
    ) -> None:
        """
        Evento: job falhou com erro.

        Args:
            job_id:     ID do job com falha
            error_msg:  Mensagem de erro descritiva
            error_type: Tipo da exceção (ex: 'ConnectionError', 'TimeoutError')
        """
        self.publish_job_event(
            job_id=job_id,
            event_type="job_failed",
            data={"error_msg": error_msg, "error_type": error_type, "status": "failed"},
        )

    def close(self) -> None:
        """Fecha a conexão Redis de forma ordenada."""
        if self._client is not None:
            try:
                self._client.close()
                logger.debug("Conexão Redis do EventPublisher encerrada.")
            except Exception:
                pass
            finally:
                self._client = None


# ---------------------------------------------------------------------------
# Instância global compartilhada (singleton para workers Celery)
# ---------------------------------------------------------------------------

_publisher_instance: EventPublisher | None = None


def get_publisher() -> EventPublisher:
    """
    Retorna a instância global do EventPublisher (lazy singleton).

    Uso:
        from worker.events import get_publisher
        get_publisher().job_started(job_id=1, url="https://example.com")
    """
    global _publisher_instance
    if _publisher_instance is None:
        _publisher_instance = EventPublisher()
    return _publisher_instance
