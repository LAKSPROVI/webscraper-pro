"""
routers/spiders.py — Endpoints de gerenciamento de configurações de spider

Endpoints:
    GET    /api/v1/spiders                      — Listar configurações
    POST   /api/v1/spiders                      — Criar nova configuração
    GET    /api/v1/spiders/{name}               — Detalhes de uma config
    PUT    /api/v1/spiders/{name}               — Atualizar config
    DELETE /api/v1/spiders/{name}               — Desativar config (soft delete)
    POST   /api/v1/spiders/{name}/validate      — Validar YAML da config
"""

import logging
from datetime import datetime, timezone
from typing import Any, Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from database.models import SpiderConfig
from database.queries import (
    create_spider_config,
    get_spider_config,
    list_spider_configs,
)
from api.models.schemas import (
    CreateSpiderConfig,
    PaginatedResponse,
    SpiderConfigResponse,
    SpiderValidationResponse,
    UpdateSpiderConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/spiders",
    tags=["Spiders"],
    responses={
        404: {"description": "Configuração não encontrada"},
        422: {"description": "Parâmetros inválidos"},
    },
)


# ---------------------------------------------------------------------------
# GET /api/v1/spiders — Listar configurações
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedResponse[SpiderConfigResponse],
    summary="Listar configurações de spider",
    description="""
    Retorna todas as configurações de spider cadastradas no sistema.

    Por padrão, retorna apenas configurações ativas (`active=True`).
    Use `include_inactive=true` para incluir configurações desativadas.
    """,
)
async def listar_spiders(
    db: Annotated[Any, Depends(get_db)],
    include_inactive: Annotated[bool, Query(description="Incluir configurações desativas")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PaginatedResponse[SpiderConfigResponse]:
    """
    Lista as configurações de spider com paginação.

    Args:
        db: Sessão do banco.
        include_inactive: Se inclui configurações desativadas.
        page: Página atual.
        limit: Itens por página.

    Returns:
        PaginatedResponse com lista de SpiderConfigResponse.
    """
    from sqlalchemy import func

    offset = (page - 1) * limit
    active_only = not include_inactive

    configs = await list_spider_configs(db, active_only=active_only, limit=limit, offset=offset)

    # Conta total
    from sqlalchemy import func as sa_func
    count_stmt = select(sa_func.count(SpiderConfig.id))
    if active_only:
        count_stmt = count_stmt.where(SpiderConfig.active.is_(True))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    items = [SpiderConfigResponse.model_validate(cfg) for cfg in configs]

    return PaginatedResponse[SpiderConfigResponse](
        items=items,
        total=total,
        page=page,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/spiders — Criar nova configuração
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=SpiderConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar configuração de spider",
    description="""
    Cria uma nova configuração de spider com YAML de definição.

    O nome deve ser único no sistema. Se já existir uma configuração com
    o mesmo nome, retornará erro 409 (conflito).
    """,
    responses={
        201: {"description": "Configuração criada com sucesso"},
        409: {"description": "Já existe uma configuração com este nome"},
    },
)
async def criar_spider(
    request: CreateSpiderConfig,
    db: Annotated[Any, Depends(get_db)],
) -> SpiderConfigResponse:
    """
    Cria uma nova configuração de spider.

    Args:
        request: Dados da nova configuração.
        db: Sessão do banco.

    Returns:
        SpiderConfigResponse com dados da configuração criada.

    Raises:
        HTTPException 409: Se o nome já estiver em uso.
        HTTPException 400: Se o YAML for inválido.
    """
    # Valida o YAML antes de salvar
    try:
        parsed = yaml.safe_load(request.config_yaml)
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O YAML deve conter um dicionário de configurações no nível raiz.",
            )
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"YAML inválido: {str(exc)}",
        ) from exc

    try:
        config = await create_spider_config(
            db,
            name=request.name,
            config_yaml=request.config_yaml,
            spider_type=request.spider_type,
            description=request.description,
        )

        logger.info("SpiderConfig criada: id=%d name=%s", config.id, config.name)
        return SpiderConfigResponse.model_validate(config)

    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Já existe uma configuração com o nome '{request.name}'. Use um nome diferente.",
        )


# ---------------------------------------------------------------------------
# GET /api/v1/spiders/{name} — Detalhes
# ---------------------------------------------------------------------------


@router.get(
    "/{name}",
    response_model=SpiderConfigResponse,
    summary="Detalhes de uma configuração de spider",
    responses={
        200: {"description": "Dados da configuração"},
        404: {"description": "Configuração não encontrada"},
    },
)
async def obter_spider(
    name: str,
    db: Annotated[Any, Depends(get_db)],
) -> SpiderConfigResponse:
    """
    Retorna os detalhes completos de uma configuração de spider.

    Args:
        name: Nome da configuração.
        db: Sessão do banco.

    Returns:
        SpiderConfigResponse com todos os dados da configuração.

    Raises:
        HTTPException 404: Se a configuração não existir.
    """
    config = await get_spider_config(db, name=name)

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuração de spider '{name}' não foi encontrada.",
        )

    return SpiderConfigResponse.model_validate(config)


# ---------------------------------------------------------------------------
# PUT /api/v1/spiders/{name} — Atualizar configuração
# ---------------------------------------------------------------------------


@router.put(
    "/{name}",
    response_model=SpiderConfigResponse,
    summary="Atualizar configuração de spider",
    description="""
    Atualiza campos de uma configuração de spider existente.

    Todos os campos são opcionais — apenas os fornecidos serão atualizados.
    """,
    responses={
        200: {"description": "Configuração atualizada"},
        404: {"description": "Configuração não encontrada"},
        400: {"description": "YAML inválido"},
    },
)
async def atualizar_spider(
    name: str,
    request: UpdateSpiderConfig,
    db: Annotated[Any, Depends(get_db)],
) -> SpiderConfigResponse:
    """
    Atualiza uma configuração de spider existente.

    Args:
        name: Nome da configuração a atualizar.
        request: Campos a atualizar (todos opcionais).
        db: Sessão do banco.

    Returns:
        SpiderConfigResponse atualizado.

    Raises:
        HTTPException 404: Se a configuração não existir.
        HTTPException 400: Se o YAML fornecido for inválido.
    """
    config = await get_spider_config(db, name=name)

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuração de spider '{name}' não foi encontrada.",
        )

    # Valida o YAML se fornecido
    if request.config_yaml is not None:
        try:
            parsed = yaml.safe_load(request.config_yaml)
            if not isinstance(parsed, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="O YAML deve conter um dicionário de configurações.",
                )
        except yaml.YAMLError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"YAML inválido: {str(exc)}",
            ) from exc

    # Constrói dict de atualizações apenas com campos fornecidos
    updates: dict = {}
    if request.config_yaml is not None:
        updates["config_yaml"] = request.config_yaml
    if request.description is not None:
        updates["description"] = request.description
    if request.spider_type is not None:
        updates["spider_type"] = request.spider_type
    if request.active is not None:
        updates["active"] = request.active

    if not updates:
        return SpiderConfigResponse.model_validate(config)

    # Adiciona timestamp de atualização
    updates["updated_at"] = datetime.now(tz=timezone.utc)

    # Executa update
    stmt = (
        update(SpiderConfig)
        .where(SpiderConfig.name == name)
        .values(**updates)
        .returning(SpiderConfig)
    )
    result = await db.execute(stmt)
    config_atualizada = result.scalar_one()

    logger.info("SpiderConfig atualizada: name=%s campos=%s", name, list(updates.keys()))
    return SpiderConfigResponse.model_validate(config_atualizada)


# ---------------------------------------------------------------------------
# DELETE /api/v1/spiders/{name} — Desativar configuração (soft delete)
# ---------------------------------------------------------------------------


@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desativar configuração de spider",
    description="""
    Desativa uma configuração de spider (soft delete — não remove do banco).

    A configuração fica inacessível nas listagens padrão, mas pode ser
    consultada com `include_inactive=true`.
    """,
    responses={
        204: {"description": "Configuração desativada"},
        404: {"description": "Configuração não encontrada"},
    },
)
async def desativar_spider(
    name: str,
    db: Annotated[Any, Depends(get_db)],
) -> None:
    """
    Desativa uma configuração de spider (soft delete).

    Args:
        name: Nome da configuração a desativar.
        db: Sessão do banco.

    Raises:
        HTTPException 404: Se a configuração não existir.
    """
    config = await get_spider_config(db, name=name)

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuração de spider '{name}' não foi encontrada.",
        )

    # Soft delete — apenas marca como inativo
    stmt = (
        update(SpiderConfig)
        .where(SpiderConfig.name == name)
        .values(active=False, updated_at=datetime.now(tz=timezone.utc))
    )
    await db.execute(stmt)

    logger.info("SpiderConfig desativada: name=%s", name)


# ---------------------------------------------------------------------------
# POST /api/v1/spiders/{name}/validate — Validar YAML
# ---------------------------------------------------------------------------


@router.post(
    "/{name}/validate",
    response_model=SpiderValidationResponse,
    summary="Validar YAML de configuração de spider",
    description="""
    Valida o YAML de uma configuração de spider existente.

    Verifica:
    - Sintaxe YAML válida
    - Campos obrigatórios presentes
    - Valores de configuração válidos

    Retorna lista de erros e avisos sem modificar a configuração.
    """,
)
async def validar_spider(
    name: str,
    db: Annotated[Any, Depends(get_db)],
) -> SpiderValidationResponse:
    """
    Valida a configuração YAML de um spider.

    Args:
        name: Nome da configuração a validar.
        db: Sessão do banco.

    Returns:
        SpiderValidationResponse com lista de erros e avisos.

    Raises:
        HTTPException 404: Se a configuração não existir.
    """
    config = await get_spider_config(db, name=name)

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Configuração de spider '{name}' não foi encontrada.",
        )

    erros: list[str] = []
    avisos: list[str] = []
    parsed_config = None

    # Valida sintaxe YAML
    try:
        parsed_config = yaml.safe_load(config.config_yaml)
    except yaml.YAMLError as exc:
        erros.append(f"Erro de sintaxe YAML: {str(exc)}")
        return SpiderValidationResponse(
            valid=False,
            errors=erros,
            warnings=avisos,
            parsed_config=None,
        )

    # Verifica estrutura do dicionário
    if not isinstance(parsed_config, dict):
        erros.append("O YAML deve conter um dicionário de configurações no nível raiz.")
        return SpiderValidationResponse(
            valid=False,
            errors=erros,
            warnings=avisos,
        )

    # Verifica campos recomendados
    if "start_url" not in parsed_config and "start_urls" not in parsed_config:
        avisos.append(
            "Nenhuma URL de início definida. Adicione 'start_url' ou 'start_urls' para execuções automáticas."
        )

    if "spider_type" not in parsed_config:
        avisos.append("Campo 'spider_type' não definido no YAML. Será usado o tipo padrão 'generic'.")

    # Valida configurações específicas por tipo de spider
    spider_type = parsed_config.get("spider_type", "generic")

    if spider_type == "playwright":
        if "render_js" not in parsed_config:
            avisos.append("Spider tipo 'playwright' recomenda definir 'render_js: true'.")

    elif spider_type == "scrapy":
        if "settings" not in parsed_config:
            avisos.append("Spider tipo 'scrapy' pode usar o campo 'settings' para configurações do Scrapy.")

    # Valida tipos de dados
    if "crawl_depth" in parsed_config:
        depth = parsed_config["crawl_depth"]
        if not isinstance(depth, int) or depth < 1 or depth > 10:
            erros.append("'crawl_depth' deve ser um inteiro entre 1 e 10.")

    if "delay" in parsed_config:
        delay = parsed_config["delay"]
        if not isinstance(delay, (int, float)) or delay < 0:
            erros.append("'delay' deve ser um número não-negativo (segundos entre requisições).")

    logger.info(
        "Validação de spider '%s': erros=%d avisos=%d",
        name,
        len(erros),
        len(avisos),
    )

    return SpiderValidationResponse(
        valid=len(erros) == 0,
        errors=erros,
        warnings=avisos,
        parsed_config=parsed_config if len(erros) == 0 else None,
    )
