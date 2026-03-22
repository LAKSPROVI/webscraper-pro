"""
celery_app.py — Configuração do cliente Celery para a API

Este módulo configura o Celery como CLIENTE (não define tasks).
A API usa este módulo apenas para enviar tarefas (.delay()) aos workers,
verificar status e revogar tasks via broker Redis.

Funções principais:
    - send_scrape_task(): Envia task de scraping para fila
    - revoke_task(): Revoga (cancela) uma task em execução
    - get_task_status(): Consulta o status atual de uma task
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from celery import Celery
from celery.result import AsyncResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração do Celery — apenas como cliente
# ---------------------------------------------------------------------------

# Lê URLs do broker e backend das variáveis de ambiente
CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

# Cria instância do Celery configurada como cliente
celery_client: Celery = Celery(
    "webscraper_api_client",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

# Configurações do Celery (apenas as necessárias para cliente)
celery_client.conf.update(
    # Serialização
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # TTL dos resultados (1 hora)
    result_expires=3600,
    # Não criar workers — apenas cliente
    task_always_eager=False,
    # Confirmação de mensagem apenas após processamento
    task_acks_late=True,
    # Não publicar estado automático (controle manual)
    task_track_started=True,
    # Máximo de retries
    task_max_retries=3,
    # Retry delay em segundos
    task_default_retry_delay=60,
)


# ---------------------------------------------------------------------------
# Funções de interface com o broker
# ---------------------------------------------------------------------------


def send_scrape_task(
    url: str,
    job_id: int,
    *,
    config_name: Optional[str] = None,
    spider_type: str = "generic",
    render_js: bool = False,
    crawl_depth: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Envia uma task de scraping para a fila do Celery.

    Usa a task 'scrape_url' definida no worker (não importada aqui,
    apenas referenciada por nome para evitar acoplamento).

    Args:
        url: URL alvo para scraping.
        job_id: ID do job já criado no banco.
        config_name: Nome da configuração de spider (opcional).
        spider_type: Tipo do spider.
        render_js: Se deve renderizar JavaScript.
        crawl_depth: Profundidade máxima de crawling.
        metadata: Metadados adicionais.

    Returns:
        task_id: UUID da task Celery criada.
    """
    # Usa .send_task() para não precisar importar a task do worker
    result = celery_client.send_task(
        "worker.tasks.scrape_url",
        args=[],
        kwargs={
            "url": url,
            "job_id": job_id,
            "config_name": config_name,
            "spider_type": spider_type,
            "render_js": render_js,
            "crawl_depth": crawl_depth,
            "metadata": metadata or {},
        },
        # Fila padrão de scraping
        queue="scraping",
        # Prioridade normal
        priority=5,
    )

    task_id: str = result.id
    logger.info(
        "Task de scraping enviada: task_id=%s job_id=%d url=%s",
        task_id,
        job_id,
        url,
    )
    return task_id


def send_bulk_scrape_task(
    urls: list[str],
    job_ids: list[int],
    *,
    config_name: Optional[str] = None,
    spider_type: str = "generic",
    render_js: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
) -> list[str]:
    """
    Envia múltiplas tasks de scraping para a fila do Celery.

    Args:
        urls: Lista de URLs para scraping.
        job_ids: Lista de IDs dos jobs correspondentes.
        config_name: Configuração de spider (mesma para todas).
        spider_type: Tipo do spider.
        render_js: Se deve renderizar JavaScript.
        metadata: Metadados comuns.

    Returns:
        Lista de task_ids criados.
    """
    task_ids: list[str] = []

    for url, job_id in zip(urls, job_ids):
        task_id = send_scrape_task(
            url=url,
            job_id=job_id,
            config_name=config_name,
            spider_type=spider_type,
            render_js=render_js,
            crawl_depth=1,
            metadata=metadata,
        )
        task_ids.append(task_id)

    logger.info(
        "Bulk scrape enviado: %d tasks para fila scraping",
        len(task_ids),
    )
    return task_ids


def revoke_task(task_id: str, *, terminate: bool = True) -> bool:
    """
    Revoga (cancela) uma task Celery em andamento ou na fila.

    Args:
        task_id: UUID da task a cancelar.
        terminate: Se True, envia SIGTERM para o worker executando a task.

    Returns:
        True se a revogação foi enviada, False em caso de erro.
    """
    try:
        celery_client.control.revoke(
            task_id,
            terminate=terminate,
            signal="SIGTERM",
        )
        logger.info("Task revogada: task_id=%s terminate=%s", task_id, terminate)
        return True
    except Exception as exc:
        logger.error("Erro ao revogar task %s: %s", task_id, exc)
        return False


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Consulta o status atual de uma task Celery no backend de resultados.

    Args:
        task_id: UUID da task a consultar.

    Returns:
        Dicionário com:
            - task_id: UUID da task
            - status: PENDING, STARTED, SUCCESS, FAILURE, REVOKED
            - result: Resultado (se SUCCESS) ou erro (se FAILURE)
            - progress: Progresso (0-100) se disponível
    """
    try:
        result: AsyncResult = AsyncResult(task_id, app=celery_client)
        status = result.status

        response: Dict[str, Any] = {
            "task_id": task_id,
            "status": status,
            "result": None,
            "progress": 0,
            "error": None,
        }

        if status == "SUCCESS":
            response["result"] = result.result
            response["progress"] = 100

        elif status == "FAILURE":
            error = result.result
            response["error"] = str(error) if error else "Erro desconhecido"
            response["progress"] = 0

        elif status == "STARTED":
            # Progresso intermediário via meta
            info = result.info
            if isinstance(info, dict):
                response["progress"] = info.get("progress", 0)

        elif status == "REVOKED":
            response["error"] = "Task cancelada pelo usuário"

        return response

    except Exception as exc:
        logger.error("Erro ao consultar status da task %s: %s", task_id, exc)
        return {
            "task_id": task_id,
            "status": "UNKNOWN",
            "result": None,
            "progress": 0,
            "error": str(exc),
        }
