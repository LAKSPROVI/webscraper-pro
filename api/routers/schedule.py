"""
routers/schedule.py — Endpoints de gerenciamento de agendamentos CRON

Endpoints:
    GET    /api/v1/schedule           — Listar agendamentos
    POST   /api/v1/schedule           — Criar agendamento
    PUT    /api/v1/schedule/{id}      — Atualizar agendamento
    DELETE /api/v1/schedule/{id}      — Deletar agendamento
    POST   /api/v1/schedule/{id}/toggle — Ativar/desativar agendamento
"""

import logging
from datetime import datetime, timezone
from typing import Any, Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from database.models import ScheduledJob
from database.queries import (
    create_scheduled_job,
    get_spider_config,
)
from models.schemas import (
    CreateScheduledJob,
    PaginatedResponse,
    ScheduledJobResponse,
    UpdateScheduledJob,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/schedule",
    tags=["Agendamentos"],
    responses={
        404: {"description": "Agendamento não encontrado"},
        422: {"description": "Parâmetros inválidos"},
    },
)


# ---------------------------------------------------------------------------
# Função auxiliar para calcular próxima execução
# ---------------------------------------------------------------------------


def _calcular_proxima_execucao(cron_expression: str) -> Optional[datetime]:
    """
    Calcula a próxima data de execução baseada na expressão CRON.

    Args:
        cron_expression: Expressão CRON no formato 'min hora dia_mes mes dia_semana'.

    Returns:
        Datetime da próxima execução, ou None se não for possível calcular.
    """
    try:
        from croniter import croniter  # type: ignore
        cron = croniter(cron_expression, datetime.now(tz=timezone.utc))
        return cron.get_next(datetime)
    except ImportError:
        # croniter não disponível — retorna None
        logger.debug("croniter não disponível para calcular próxima execução")
        return None
    except Exception as exc:
        logger.warning("Erro ao calcular próxima execução para '%s': %s", cron_expression, exc)
        return None


# ---------------------------------------------------------------------------
# GET /api/v1/schedule — Listar agendamentos
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedResponse[ScheduledJobResponse],
    summary="Listar agendamentos",
    description="""
    Retorna todos os agendamentos cadastrados no sistema.

    Por padrão, retorna apenas agendamentos habilitados.
    Use `include_disabled=true` para incluir agendamentos desabilitados.
    """,
)
async def listar_agendamentos(
    db: Annotated[Any, Depends(get_db)],
    include_disabled: Annotated[bool, Query(description="Incluir agendamentos desabilitados")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[ScheduledJobResponse]:
    """
    Lista os agendamentos com paginação.

    Args:
        db: Sessão do banco.
        include_disabled: Se inclui agendamentos desabilitados.
        page: Página atual.
        limit: Itens por página.

    Returns:
        PaginatedResponse com lista de ScheduledJobResponse.
    """
    offset = (page - 1) * limit

    # Monta query
    stmt = select(ScheduledJob)
    if not include_disabled:
        stmt = stmt.where(ScheduledJob.enabled.is_(True))

    stmt = stmt.order_by(ScheduledJob.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    agendamentos = result.scalars().all()

    # Conta total
    count_stmt = select(func.count(ScheduledJob.id))
    if not include_disabled:
        count_stmt = count_stmt.where(ScheduledJob.enabled.is_(True))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    items = [ScheduledJobResponse.model_validate(ag) for ag in agendamentos]

    return PaginatedResponse[ScheduledJobResponse](
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/schedule — Criar agendamento
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ScheduledJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar agendamento",
    description="""
    Cria um novo agendamento de scraping com expressão CRON.

    Exemplos de expressão CRON:
    - `0 6 * * *` — Todos os dias às 6h
    - `0 */6 * * *` — A cada 6 horas
    - `*/30 * * * *` — A cada 30 minutos
    - `0 9 * * 1-5` — Dias úteis às 9h

    A próxima execução é calculada automaticamente ao criar o agendamento.
    """,
    responses={
        201: {"description": "Agendamento criado com sucesso"},
        404: {"description": "Configuração de spider não encontrada"},
    },
)
async def criar_agendamento(
    request: CreateScheduledJob,
    db: Annotated[Any, Depends(get_db)],
) -> ScheduledJobResponse:
    """
    Cria um novo agendamento de scraping.

    Args:
        request: Dados do agendamento (nome, spider_config_id, cron).
        db: Sessão do banco.

    Returns:
        ScheduledJobResponse com dados do agendamento criado.

    Raises:
        HTTPException 404: Se a configuração de spider não existir.
    """
    # Verifica se a configuração de spider existe
    config = await get_spider_config(db, config_id=request.spider_config_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuração de spider com ID {request.spider_config_id} não foi encontrada.",
        )

    if not config.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A configuração de spider ID {request.spider_config_id} está desativada. Ative-a antes de criar um agendamento.",
        )

    # Calcula próxima execução
    proxima_execucao = _calcular_proxima_execucao(request.cron_expression)

    agendamento = await create_scheduled_job(
        db,
        name=request.name,
        spider_config_id=request.spider_config_id,
        cron_expression=request.cron_expression,
        enabled=request.enabled,
        next_run=proxima_execucao,
    )

    logger.info(
        "Agendamento criado: id=%d name=%s cron=%s next_run=%s",
        agendamento.id,
        agendamento.name,
        agendamento.cron_expression,
        proxima_execucao,
    )

    return ScheduledJobResponse.model_validate(agendamento)


# ---------------------------------------------------------------------------
# PUT /api/v1/schedule/{id} — Atualizar agendamento
# ---------------------------------------------------------------------------


@router.put(
    "/{schedule_id}",
    response_model=ScheduledJobResponse,
    summary="Atualizar agendamento",
    description="""
    Atualiza um agendamento existente.

    Se a expressão CRON for alterada, a próxima execução é recalculada automaticamente.
    """,
    responses={
        200: {"description": "Agendamento atualizado"},
        404: {"description": "Agendamento não encontrado"},
    },
)
async def atualizar_agendamento(
    schedule_id: int,
    request: UpdateScheduledJob,
    db: Annotated[Any, Depends(get_db)],
) -> ScheduledJobResponse:
    """
    Atualiza um agendamento existente.

    Args:
        schedule_id: ID do agendamento a atualizar.
        request: Campos a atualizar.
        db: Sessão do banco.

    Returns:
        ScheduledJobResponse atualizado.

    Raises:
        HTTPException 404: Se o agendamento não existir.
    """
    # Verifica se o agendamento existe
    stmt_check = select(ScheduledJob).where(ScheduledJob.id == schedule_id)
    result = await db.execute(stmt_check)
    agendamento = result.scalar_one_or_none()

    if agendamento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agendamento com ID {schedule_id} não foi encontrado.",
        )

    # Constrói dict de atualizações
    updates: dict = {}

    if request.name is not None:
        updates["name"] = request.name

    if request.enabled is not None:
        updates["enabled"] = request.enabled

    if request.spider_config_id is not None:
        # Verifica se a nova configuração existe
        nova_config = await get_spider_config(db, config_id=request.spider_config_id)
        if nova_config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuração de spider com ID {request.spider_config_id} não foi encontrada.",
            )
        updates["spider_config_id"] = request.spider_config_id

    if request.cron_expression is not None:
        updates["cron_expression"] = request.cron_expression
        # Recalcula próxima execução com nova expressão CRON
        proxima = _calcular_proxima_execucao(request.cron_expression)
        if proxima:
            updates["next_run"] = proxima

    if not updates:
        return ScheduledJobResponse.model_validate(agendamento)

    # Executa atualização
    stmt = (
        update(ScheduledJob)
        .where(ScheduledJob.id == schedule_id)
        .values(**updates)
        .returning(ScheduledJob)
    )
    result = await db.execute(stmt)
    ag_atualizado = result.scalar_one()

    logger.info("Agendamento atualizado: id=%d campos=%s", schedule_id, list(updates.keys()))
    return ScheduledJobResponse.model_validate(ag_atualizado)


# ---------------------------------------------------------------------------
# DELETE /api/v1/schedule/{id} — Deletar agendamento
# ---------------------------------------------------------------------------


@router.delete(
    "/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deletar agendamento",
    description="Remove permanentemente um agendamento do sistema.",
    responses={
        204: {"description": "Agendamento deletado"},
        404: {"description": "Agendamento não encontrado"},
    },
)
async def deletar_agendamento(
    schedule_id: int,
    db: Annotated[Any, Depends(get_db)],
) -> None:
    """
    Deleta permanentemente um agendamento.

    Args:
        schedule_id: ID do agendamento a deletar.
        db: Sessão do banco.

    Raises:
        HTTPException 404: Se o agendamento não existir.
    """
    # Verifica se existe
    stmt_check = select(ScheduledJob.id).where(ScheduledJob.id == schedule_id).limit(1)
    result = await db.execute(stmt_check)
    existe = result.scalar_one_or_none()

    if existe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agendamento com ID {schedule_id} não foi encontrado.",
        )

    # Deleta
    stmt_delete = delete(ScheduledJob).where(ScheduledJob.id == schedule_id)
    await db.execute(stmt_delete)

    logger.info("Agendamento deletado: id=%d", schedule_id)


# ---------------------------------------------------------------------------
# POST /api/v1/schedule/{id}/toggle — Ativar/desativar
# ---------------------------------------------------------------------------


@router.post(
    "/{schedule_id}/toggle",
    response_model=ScheduledJobResponse,
    summary="Ativar/desativar agendamento",
    description="""
    Alterna o estado do agendamento entre ativo e inativo.

    - Se estava ativo (`enabled=true`), será desativado
    - Se estava inativo (`enabled=false`), será ativado e a próxima execução é recalculada
    """,
    responses={
        200: {"description": "Estado do agendamento alterado"},
        404: {"description": "Agendamento não encontrado"},
    },
)
async def toggle_agendamento(
    schedule_id: int,
    db: Annotated[Any, Depends(get_db)],
) -> ScheduledJobResponse:
    """
    Alterna o estado de habilitação de um agendamento.

    Args:
        schedule_id: ID do agendamento.
        db: Sessão do banco.

    Returns:
        ScheduledJobResponse com novo estado.

    Raises:
        HTTPException 404: Se o agendamento não existir.
    """
    # Busca o agendamento atual
    stmt_check = select(ScheduledJob).where(ScheduledJob.id == schedule_id)
    result = await db.execute(stmt_check)
    agendamento = result.scalar_one_or_none()

    if agendamento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agendamento com ID {schedule_id} não foi encontrado.",
        )

    # Inverte o estado
    novo_estado = not agendamento.enabled
    updates: dict = {"enabled": novo_estado}

    # Se ativando, recalcula próxima execução
    if novo_estado:
        proxima = _calcular_proxima_execucao(agendamento.cron_expression)
        if proxima:
            updates["next_run"] = proxima

    # Aplica o toggle
    stmt = (
        update(ScheduledJob)
        .where(ScheduledJob.id == schedule_id)
        .values(**updates)
        .returning(ScheduledJob)
    )
    result = await db.execute(stmt)
    ag_atualizado = result.scalar_one()

    acao = "ativado" if novo_estado else "desativado"
    logger.info("Agendamento %s: id=%d", acao, schedule_id)

    return ScheduledJobResponse.model_validate(ag_atualizado)
