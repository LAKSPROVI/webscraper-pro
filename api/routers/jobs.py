"""
routers/jobs.py — Endpoints de gerenciamento de jobs + WebSocket

Endpoints REST:
    GET    /api/v1/jobs                     — Listar jobs com filtros
    GET    /api/v1/jobs/{job_id}            — Detalhes de um job
    DELETE /api/v1/jobs/{job_id}            — Cancelar um job
    GET    /api/v1/jobs/{job_id}/items      — Items coletados do job

WebSocket:
    WS /api/v1/ws/jobs — Stream de updates de todos os jobs em tempo real
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Annotated, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webscraper.database.connection import get_db
from webscraper.database.models import JobStatus, ScrapedItem, ScrapingJob
from webscraper.database.queries import (
    get_items_by_job,
    get_job,
    list_jobs,
    update_job_status,
)
from webscraper.api.models.celery_app import revoke_task
from webscraper.api.models.schemas import (
    ItemResponse,
    JobResponse,
    PaginatedResponse,
)

logger = logging.getLogger(__name__)

# URL do Redis para pub/sub de eventos de jobs
REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")

router = APIRouter(
    prefix="/api/v1",
    tags=["Jobs"],
    responses={
        404: {"description": "Job não encontrado"},
        422: {"description": "Parâmetros inválidos"},
    },
)


# ---------------------------------------------------------------------------
# GET /api/v1/jobs — Listar jobs com paginação e filtros
# ---------------------------------------------------------------------------


@router.get(
    "/jobs",
    response_model=PaginatedResponse[JobResponse],
    summary="Listar jobs de scraping",
    description="""
    Retorna uma lista paginada de jobs com suporte a filtros por status.

    Ordenação padrão: mais recentes primeiro (created_at DESC).
    """,
)
async def listar_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filtro: Annotated[
        Optional[str],
        Query(alias="status", description="Filtrar por status: pending, running, done, failed, cancelled"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Página atual (começa em 1)")] = 1,
    limit: Annotated[int, Query(ge=1, le=100, description="Itens por página (máx. 100)")] = 20,
    order_by: Annotated[
        str,
        Query(description="Campo de ordenação: created_at, status, items_scraped"),
    ] = "created_at",
) -> PaginatedResponse[JobResponse]:
    """
    Lista todos os jobs com suporte a paginação e filtros.

    Args:
        db: Sessão do banco de dados.
        status_filtro: Filtra por status específico (opcional).
        page: Número da página (começa em 1).
        limit: Quantidade de itens por página.
        order_by: Campo para ordenação.

    Returns:
        PaginatedResponse com lista de JobResponse e metadados de paginação.
    """
    # Valida o status se fornecido
    status_enum: Optional[JobStatus] = None
    if status_filtro:
        try:
            status_enum = JobStatus(status_filtro)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Status inválido: '{status_filtro}'. Use um de: {[s.value for s in JobStatus]}",
            )

    offset = (page - 1) * limit

    # Busca os jobs com paginação
    jobs = await list_jobs(
        db,
        status=status_enum,
        limit=limit,
        offset=offset,
        order_desc=(order_by == "created_at"),
    )

    # Conta o total para metadados de paginação
    count_stmt = select(func.count(ScrapingJob.id))
    if status_enum:
        count_stmt = count_stmt.where(ScrapingJob.status == status_enum.value)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Converte models para response schemas
    items = [JobResponse.model_validate(job) for job in jobs]

    return PaginatedResponse[JobResponse](
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id} — Detalhes de um job
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    summary="Detalhes de um job",
    description="Retorna todos os dados de um job específico, incluindo duração calculada e estatísticas.",
    responses={
        200: {"description": "Dados do job"},
        404: {"description": "Job não encontrado"},
    },
)
async def obter_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobResponse:
    """
    Retorna os detalhes completos de um job de scraping.

    Args:
        job_id: ID do job a consultar.
        db: Sessão do banco de dados.

    Returns:
        JobResponse com todos os dados do job.

    Raises:
        HTTPException 404: Se o job não existir.
    """
    job = await get_job(db, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job com ID {job_id} não foi encontrado.",
        )

    return JobResponse.model_validate(job)


# ---------------------------------------------------------------------------
# DELETE /api/v1/jobs/{job_id} — Cancelar job
# ---------------------------------------------------------------------------


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancelar um job",
    description="""
    Cancela um job em execução ou na fila.

    - Revoga a task Celery correspondente
    - Atualiza o status do job para 'cancelled' no banco de dados
    - Jobs já concluídos ou cancelados não podem ser cancelados novamente
    """,
    responses={
        204: {"description": "Job cancelado com sucesso"},
        404: {"description": "Job não encontrado"},
        409: {"description": "Job já concluído ou cancelado"},
    },
)
async def cancelar_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """
    Cancela um job de scraping.

    Args:
        job_id: ID do job a cancelar.
        db: Sessão do banco de dados.

    Raises:
        HTTPException 404: Se o job não existir.
        HTTPException 409: Se o job já estiver concluído ou cancelado.
    """
    job = await get_job(db, job_id)

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job com ID {job_id} não foi encontrado.",
        )

    # Verifica se o job pode ser cancelado
    status_nao_cancelaveis = {JobStatus.DONE.value, JobStatus.CANCELLED.value}
    if job.status in status_nao_cancelaveis:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job {job_id} não pode ser cancelado pois está com status '{job.status}'.",
        )

    # Tenta revogar a task Celery (se houver task_id nos metadados)
    task_id = None
    if job.metadata_ and isinstance(job.metadata_, dict):
        task_id = job.metadata_.get("celery_task_id")

    if task_id:
        revoke_task(task_id, terminate=True)
        logger.info("Task Celery revogada: task_id=%s job_id=%d", task_id, job_id)

    # Atualiza status para cancelado no banco
    await update_job_status(db, job_id, JobStatus.CANCELLED)

    logger.info("Job cancelado: job_id=%d", job_id)


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id}/items — Items coletados
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}/items",
    response_model=PaginatedResponse[ItemResponse],
    summary="Items coletados por job",
    description="Retorna todos os itens coletados durante a execução de um job específico.",
    responses={
        200: {"description": "Lista de itens coletados"},
        404: {"description": "Job não encontrado"},
    },
)
async def listar_items_do_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[ItemResponse]:
    """
    Lista os itens coletados por um job específico.

    Args:
        job_id: ID do job.
        db: Sessão do banco de dados.
        page: Número da página.
        limit: Itens por página.

    Returns:
        PaginatedResponse com lista de ItemResponse.

    Raises:
        HTTPException 404: Se o job não existir.
    """
    # Verifica se o job existe
    job = await get_job(db, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job com ID {job_id} não foi encontrado.",
        )

    offset = (page - 1) * limit

    # Busca os items do job
    items_db = await get_items_by_job(db, job_id, limit=limit, offset=offset)

    # Conta total de items
    count_stmt = select(func.count(ScrapedItem.id)).where(ScrapedItem.job_id == job_id)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Converte para response schema com conteúdo truncado para listagem
    items = []
    for item in items_db:
        item_resp = ItemResponse.model_validate(item)
        item_resp = item_resp.truncar_content(max_chars=300)
        items.append(item_resp)

    return PaginatedResponse[ItemResponse](
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# WebSocket /api/v1/ws/jobs — Stream de updates em tempo real
# ---------------------------------------------------------------------------


class WebSocketManager:
    """Gerenciador de conexões WebSocket ativas."""

    def __init__(self) -> None:
        self.conexoes_ativas: list[WebSocket] = []

    async def conectar(self, websocket: WebSocket) -> None:
        """Aceita e registra uma nova conexão WebSocket."""
        await websocket.accept()
        self.conexoes_ativas.append(websocket)
        logger.info("Nova conexão WebSocket. Total ativo: %d", len(self.conexoes_ativas))

    def desconectar(self, websocket: WebSocket) -> None:
        """Remove uma conexão WebSocket encerrada."""
        if websocket in self.conexoes_ativas:
            self.conexoes_ativas.remove(websocket)
        logger.info("Conexão WebSocket encerrada. Total ativo: %d", len(self.conexoes_ativas))

    async def broadcast(self, mensagem: dict) -> None:
        """Envia uma mensagem para todas as conexões ativas."""
        conexoes_para_remover: list[WebSocket] = []

        for conexao in self.conexoes_ativas:
            try:
                await conexao.send_json(mensagem)
            except Exception:
                # Conexão encerrada — marca para remoção
                conexoes_para_remover.append(conexao)

        # Remove conexões mortas
        for conexao in conexoes_para_remover:
            self.desconectar(conexao)


# Instância global do gerenciador de WebSocket
ws_manager = WebSocketManager()


@router.websocket("/ws/jobs")
async def websocket_jobs(websocket: WebSocket) -> None:
    """
    WebSocket para stream de updates de jobs em tempo real.

    Eventos enviados:
        - job_created: Quando um novo job é criado
        - job_started: Quando um job começa a executar
        - job_progress: Progresso durante a execução
        - job_done: Quando um job conclui com sucesso
        - job_failed: Quando um job falha

    Reconexão automática:
        O cliente deve tentar reconectar em caso de desconexão.
        Recomenda-se aguardar 5 segundos antes de reconectar.

    Exemplo de mensagem recebida:
        {
            "event": "job_done",
            "job_id": 42,
            "data": {"items_scraped": 150, "duration_seconds": 45.2},
            "timestamp": "2024-01-15T10:30:00Z"
        }
    """
    await ws_manager.conectar(websocket)

    # Envia mensagem de boas-vindas
    await websocket.send_json({
        "event": "connected",
        "job_id": 0,
        "data": {
            "message": "Conectado ao stream de jobs. Aguardando eventos...",
            "conexoes_ativas": len(ws_manager.conexoes_ativas),
        },
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })

    # Cria conexão Redis para pub/sub
    redis_client: Optional[aioredis.Redis] = None

    try:
        redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("webscraper:jobs:events")

        logger.info("WebSocket conectado ao canal Redis: webscraper:jobs:events")

        # Loop de escuta de eventos do Redis
        while True:
            try:
                # Aguarda mensagem com timeout de 1 segundo (permite verificar desconexão)
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=1.0,
                )

                if message and message.get("type") == "message":
                    # Encaminha evento do Redis para o cliente WebSocket
                    try:
                        evento = json.loads(message["data"])
                        await websocket.send_json(evento)
                    except json.JSONDecodeError:
                        logger.warning("Mensagem Redis inválida: %s", message["data"])

                # Verifica se o cliente ainda está conectado (ping/pong)
                # A cada 30s envia heartbeat
                elif message is None:
                    await asyncio.sleep(0.1)

            except asyncio.TimeoutError:
                # Timeout normal — envia heartbeat para manter conexão viva
                try:
                    await websocket.send_json({
                        "event": "heartbeat",
                        "job_id": 0,
                        "data": {"timestamp": datetime.now(tz=timezone.utc).isoformat()},
                        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                    })
                except Exception:
                    # Cliente desconectou durante heartbeat
                    break

    except WebSocketDisconnect:
        logger.info("Cliente WebSocket desconectado normalmente")

    except Exception as exc:
        logger.error("Erro no WebSocket: %s", exc, exc_info=True)
        try:
            await websocket.send_json({
                "event": "error",
                "job_id": 0,
                "data": {"message": "Erro interno. Reconecte em 5 segundos."},
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            })
        except Exception:
            pass

    finally:
        ws_manager.desconectar(websocket)
        if redis_client:
            try:
                await pubsub.unsubscribe("webscraper:jobs:events")
                await redis_client.aclose()
            except Exception:
                pass
