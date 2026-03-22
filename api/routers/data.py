"""
routers/data.py — Endpoints de consulta e exportação de dados coletados

Endpoints:
    GET    /api/v1/data/search          — Busca full-text nos dados
    GET    /api/v1/data/item/{item_id}  — Item específico completo
    GET    /api/v1/data/domains         — Domínios scrapeados com estatísticas
    GET    /api/v1/data/export/{format} — Exportar dados (json ou csv)
    DELETE /api/v1/data/item/{item_id}  — Deletar item específico
"""

import csv
import hashlib
import io
import logging
import time
from datetime import datetime
from typing import Any, Annotated, AsyncGenerator, Literal, Optional

import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from database.models import ScrapedItem, ScrapingJob
from models.schemas import (
    DomainStats,
    ItemResponse,
    SearchResponse,
)
from rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/data",
    tags=["Dados"],
    responses={
        404: {"description": "Item não encontrado"},
        422: {"description": "Parâmetros inválidos"},
    },
)


# ---------------------------------------------------------------------------
# GET /api/v1/data/search — Busca full-text
# ---------------------------------------------------------------------------


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Busca full-text nos dados coletados",
    description="""
    Realiza busca textual nos campos `título` e `conteúdo` dos itens coletados.

    Suporta filtros adicionais por:
    - `domain`: Filtrar por domínio de origem
    - `spider_type`: Filtrar pelo tipo de spider utilizado
    - `date_from` e `date_to`: Intervalo de datas de coleta

    O campo `query_time_ms` informa o tempo de execução da query.
    """,
)
@limiter.limit("90/minute")
async def buscar_dados(
    request: Request,
    db: Annotated[Any, Depends(get_db)],
    q: Annotated[str, Query(min_length=2, description="Termo de busca (mínimo 2 caracteres)")],
    domain: Annotated[Optional[str], Query(description="Filtrar por domínio (ex: tjsp.jus.br)")] = None,
    spider_type: Annotated[Optional[str], Query(description="Filtrar por tipo de spider")] = None,
    date_from: Annotated[Optional[datetime], Query(description="Data inicial (ISO 8601)")] = None,
    date_to: Annotated[Optional[datetime], Query(description="Data final (ISO 8601)")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SearchResponse:
    """
    Busca full-text nos dados coletados.

    Args:
        db: Sessão do banco.
        q: Termo de busca.
        domain: Filtro por domínio.
        spider_type: Filtro por tipo de spider.
        date_from: Data inicial para filtro.
        date_to: Data final para filtro.
        page: Página atual.
        limit: Itens por página.

    Returns:
        SearchResponse com itens encontrados e tempo de execução.
    """
    inicio = time.perf_counter()
    offset = (page - 1) * limit

    # Monta a query base com busca textual
    like_pattern = f"%{q}%"
    stmt = select(ScrapedItem).where(
        or_(
            ScrapedItem.title.ilike(like_pattern),
            ScrapedItem.content.ilike(like_pattern),
        )
    )

    # Aplica filtros opcionais
    if domain:
        stmt = stmt.where(ScrapedItem.domain == domain)

    if date_from:
        stmt = stmt.where(ScrapedItem.scraped_at >= date_from)

    if date_to:
        stmt = stmt.where(ScrapedItem.scraped_at <= date_to)

    if spider_type:
        # Filtra via join com scraping_jobs
        stmt = stmt.join(ScrapingJob, ScrapedItem.job_id == ScrapingJob.id)
        stmt = stmt.where(ScrapingJob.spider_type == spider_type)

    # Conta total antes da paginação
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Aplica paginação e ordenação
    stmt = stmt.order_by(ScrapedItem.scraped_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    items_db = result.scalars().all()

    # Converte para schemas com truncamento
    items = []
    for item in items_db:
        item_resp = ItemResponse.model_validate(item)
        item_resp = item_resp.truncar_content(max_chars=500)
        items.append(item_resp)

    tempo_ms = (time.perf_counter() - inicio) * 1000

    logger.info(
        "Busca realizada: q='%s' total=%d tempo=%.1fms",
        q,
        total,
        tempo_ms,
    )

    return SearchResponse(
        results=items,
        total=total,
        query_time_ms=round(tempo_ms, 2),
        query=q,
        page=page,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/data/item/{item_id} — Item específico
# ---------------------------------------------------------------------------


@router.get(
    "/item/{item_id}",
    response_model=ItemResponse,
    summary="Obter item específico",
    description="Retorna todos os dados de um item coletado, incluindo conteúdo completo e dados brutos.",
    responses={
        200: {"description": "Dados completos do item"},
        404: {"description": "Item não encontrado"},
    },
)
@limiter.limit("180/minute")
async def obter_item(
    request: Request,
    item_id: int,
    db: Annotated[Any, Depends(get_db)],
) -> ItemResponse:
    """
    Retorna os dados completos de um item coletado.

    Args:
        item_id: ID do item a consultar.
        db: Sessão do banco de dados.

    Returns:
        ItemResponse com todos os campos, incluindo conteúdo completo.

    Raises:
        HTTPException 404: Se o item não existir.
    """
    stmt = select(ScrapedItem).where(ScrapedItem.id == item_id)
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item com ID {item_id} não foi encontrado.",
        )

    # Retorna sem truncamento (dados completos)
    return ItemResponse.model_validate(item)


# ---------------------------------------------------------------------------
# GET /api/v1/data/domains — Domínios scrapeados
# ---------------------------------------------------------------------------


@router.get(
    "/domains",
    response_model=list[DomainStats],
    summary="Listar domínios scrapeados",
    description="""
    Retorna uma lista de todos os domínios que foram scrapeados,
    com contagem de itens e data da última coleta.

    Ordenado por total de itens (mais coletados primeiro).
    """,
)
@limiter.limit("60/minute")
async def listar_dominios(
    request: Request,
    response: Response,
    db: Annotated[Any, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200, description="Máximo de domínios")] = 50,
) -> list[DomainStats]:
    """
    Lista os domínios scrapeados com estatísticas.

    Args:
        db: Sessão do banco de dados.
        limit: Número máximo de domínios a retornar.

    Returns:
        Lista de DomainStats ordenada por total de itens.
    """
    response.headers["Cache-Control"] = "public, max-age=120"

    # Agrupa por domínio e calcula estatísticas
    stmt = (
        select(
            ScrapedItem.domain,
            func.count(ScrapedItem.id).label("total_items"),
            func.max(ScrapedItem.scraped_at).label("last_scraped"),
        )
        .where(ScrapedItem.domain.isnot(None))
        .group_by(ScrapedItem.domain)
        .order_by(func.count(ScrapedItem.id).desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    rows = result.all()

    payload = [
        DomainStats(
            domain=row.domain,
            total_items=row.total_items,
            last_scraped=row.last_scraped,
        )
        for row in rows
    ]

    etag = hashlib.md5(orjson.dumps([item.model_dump(mode="json") for item in payload])).hexdigest()
    response.headers["ETag"] = f'"{etag}"'
    response.headers["Last-Modified"] = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    return payload


# ---------------------------------------------------------------------------
# GET /api/v1/data/export/{format} — Exportar dados
# ---------------------------------------------------------------------------


async def _gerar_json_stream(
    items: list[ScrapedItem],
    meta: dict,
) -> AsyncGenerator[bytes, None]:
    """
    Gerador assíncrono para streaming de exportação JSON.

    Args:
        items: Lista de itens a exportar.
        meta: Metadados da exportação.

    Yields:
        Chunks de bytes do JSON.
    """
    # Cabeçalho do JSON
    yield b'{"meta": '
    yield orjson.dumps(meta)
    yield b', "items": ['

    for i, item in enumerate(items):
        item_dict = {
            "id": item.id,
            "job_id": item.job_id,
            "url": item.url,
            "title": item.title,
            "content": item.content,
            "domain": item.domain,
            "content_hash": item.content_hash,
            "scraped_at": item.scraped_at.isoformat() if item.scraped_at else None,
            "raw_data": item.raw_data,
            "metadata": item.metadata_,
        }
        chunk = orjson.dumps(item_dict)
        if i < len(items) - 1:
            yield chunk + b","
        else:
            yield chunk

    yield b"]}"


async def _gerar_csv_stream(
    items: list[ScrapedItem],
) -> AsyncGenerator[bytes, None]:
    """
    Gerador assíncrono para streaming de exportação CSV.

    Args:
        items: Lista de itens a exportar.

    Yields:
        Chunks de bytes do CSV.
    """
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["id", "job_id", "url", "title", "content", "domain", "content_hash", "scraped_at"],
        quoting=csv.QUOTE_ALL,
    )

    # Header
    writer.writeheader()
    header = output.getvalue()
    output.seek(0)
    output.truncate()
    yield header.encode("utf-8-sig")  # BOM para Excel

    # Rows
    for item in items:
        writer.writerow({
            "id": item.id,
            "job_id": item.job_id,
            "url": item.url,
            "title": item.title or "",
            "content": (item.content or "")[:5000],  # Trunca para CSV
            "domain": item.domain or "",
            "content_hash": item.content_hash,
            "scraped_at": item.scraped_at.isoformat() if item.scraped_at else "",
        })
        row = output.getvalue()
        output.seek(0)
        output.truncate()
        yield row.encode("utf-8")


@router.get(
    "/export/{format}",
    summary="Exportar dados coletados",
    description="""
    Exporta os dados coletados em formato JSON ou CSV para download.

    Suporta filtros por job, domínio e intervalo de datas.
    Limite máximo de 10.000 itens por exportação.

    **Formatos suportados:**
    - `json`: JSON estruturado com metadados da exportação
    - `csv`: CSV com BOM UTF-8 (compatível com Excel)
    """,
    responses={
        200: {"description": "Arquivo para download"},
        400: {"description": "Formato inválido ou filtros incorretos"},
    },
)
@limiter.limit("20/minute")
async def exportar_dados(
    request: Request,
    format: Literal["json", "csv"],
    db: Annotated[Any, Depends(get_db)],
    job_id: Annotated[Optional[int], Query(description="Filtrar por job")] = None,
    domain: Annotated[Optional[str], Query(description="Filtrar por domínio")] = None,
    date_from: Annotated[Optional[datetime], Query(description="Data inicial")] = None,
    date_to: Annotated[Optional[datetime], Query(description="Data final")] = None,
    limit: Annotated[int, Query(ge=1, le=10000, description="Máximo de itens")] = 1000,
) -> StreamingResponse:
    """
    Exporta dados coletados como StreamingResponse para download.

    Args:
        format: Formato de exportação (json ou csv).
        db: Sessão do banco de dados.
        job_id: Filtrar por job específico.
        domain: Filtrar por domínio.
        date_from: Data inicial para filtro.
        date_to: Data final para filtro.
        limit: Máximo de itens na exportação.

    Returns:
        StreamingResponse com o arquivo para download.
    """
    response_headers = {"Cache-Control": "no-store"}

    # Monta query de busca
    stmt = select(ScrapedItem).order_by(ScrapedItem.scraped_at.desc())

    if job_id:
        stmt = stmt.where(ScrapedItem.job_id == job_id)
    if domain:
        stmt = stmt.where(ScrapedItem.domain == domain)
    if date_from:
        stmt = stmt.where(ScrapedItem.scraped_at >= date_from)
    if date_to:
        stmt = stmt.where(ScrapedItem.scraped_at <= date_to)

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    # Metadados da exportação
    timestamp_agora = datetime.utcnow().isoformat()
    meta = {
        "format": format,
        "total_items": len(items),
        "generated_at": timestamp_agora,
        "filters": {
            "job_id": job_id,
            "domain": domain,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "limit": limit,
        },
    }

    # Gera nome do arquivo
    nome_arquivo = f"webscraper_export_{timestamp_agora[:10]}"

    logger.info(
        "Exportação iniciada: format=%s total=%d",
        format,
        len(items),
    )

    if format == "json":
        return StreamingResponse(
            _gerar_json_stream(items, meta),
            media_type="application/json",
            headers={
                **response_headers,
                "Content-Disposition": f'attachment; filename="{nome_arquivo}.json"',
                "X-Total-Items": str(len(items)),
            },
        )
    else:  # csv
        return StreamingResponse(
            _gerar_csv_stream(items),
            media_type="text/csv; charset=utf-8",
            headers={
                **response_headers,
                "Content-Disposition": f'attachment; filename="{nome_arquivo}.csv"',
                "X-Total-Items": str(len(items)),
            },
        )


# ---------------------------------------------------------------------------
# DELETE /api/v1/data/item/{item_id} — Deletar item
# ---------------------------------------------------------------------------


@router.delete(
    "/item/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deletar item coletado",
    description="Remove permanentemente um item coletado do banco de dados.",
    responses={
        204: {"description": "Item deletado com sucesso"},
        404: {"description": "Item não encontrado"},
    },
)
@limiter.limit("30/minute")
async def deletar_item(
    request: Request,
    item_id: int,
    db: Annotated[Any, Depends(get_db)],
) -> None:
    """
    Deleta permanentemente um item coletado.

    Args:
        item_id: ID do item a deletar.
        db: Sessão do banco de dados.

    Raises:
        HTTPException 404: Se o item não existir.
    """
    # Verifica se o item existe
    stmt_check = select(ScrapedItem.id).where(ScrapedItem.id == item_id).limit(1)
    result = await db.execute(stmt_check)
    existe = result.scalar_one_or_none()

    if existe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item com ID {item_id} não foi encontrado.",
        )

    # Deleta o item
    stmt_delete = delete(ScrapedItem).where(ScrapedItem.id == item_id)
    await db.execute(stmt_delete)

    logger.info("Item deletado: item_id=%d", item_id)
