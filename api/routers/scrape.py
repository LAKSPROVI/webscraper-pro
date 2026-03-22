"""
routers/scrape.py — Endpoints de disparo de scraping imediato

Endpoints:
    POST /api/v1/scrape          — Dispara scraping imediato de uma URL
    POST /api/v1/scrape/bulk     — Scraping de múltiplas URLs em lote
    POST /api/v1/scrape/preview  — Preview de extração sem salvar

Todos os endpoints são assíncronos e integram com Celery para
processamento em background.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from database.queries import create_job
from models.celery_app import send_scrape_task, send_bulk_scrape_task
from rate_limiter import limiter
from models.schemas import (
    BulkJobCreatedResponse,
    BulkScrapeRequest,
    JobCreatedResponse,
    PreviewRequest,
    PreviewResponse,
    ScrapeRequest,
)

logger = logging.getLogger(__name__)

# Cria o router com prefixo e tags para o Swagger
router = APIRouter(
    prefix="/api/v1/scrape",
    tags=["Scraping"],
    responses={
        422: {"description": "Erro de validação nos dados enviados"},
        500: {"description": "Erro interno do servidor"},
    },
)


# ---------------------------------------------------------------------------
# POST /api/v1/scrape — Disparo imediato de scraping
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=JobCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Disparar scraping de uma URL",
    description="""
    Cria um job de scraping e envia para processamento assíncrono via Celery.

    O job é criado imediatamente com status `pending` e processado em background.
    Use o endpoint `/api/v1/jobs/{job_id}` para acompanhar o progresso.
    """,
    responses={
        201: {"description": "Job criado e enviado para processamento"},
        400: {"description": "URL inválida ou parâmetros incorretos"},
    },
)
@limiter.limit("20/minute")
async def criar_scrape(
    request: Request,
    payload: ScrapeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobCreatedResponse:
    """
    Dispara um scraping imediato de uma URL.

    Args:
        request: Dados do scraping (URL, configurações, etc.).
        db: Sessão do banco de dados (injetada automaticamente).

    Returns:
        JobCreatedResponse com o ID do job e status inicial.

    Raises:
        HTTPException 400: Se a URL for inválida ou inacessível.
        HTTPException 500: Se houver erro ao criar o job ou enviar para o broker.
    """
    try:
        # Cria o registro do job no banco de dados
        job = await create_job(
            db,
            url=payload.url,
            config_name=payload.config_name,
            spider_type=payload.spider_type,
            render_js=payload.render_js,
            crawl_depth=payload.crawl_depth,
            metadata=payload.metadata if payload.metadata else None,
        )

        # Envia a task para o broker Celery
        task_id = send_scrape_task(
            url=payload.url,
            job_id=job.id,
            config_name=payload.config_name,
            spider_type=payload.spider_type,
            render_js=payload.render_js,
            crawl_depth=payload.crawl_depth,
            metadata=payload.metadata,
        )

        logger.info(
            "Scraping disparado: job_id=%d task_id=%s url=%s",
            job.id,
            task_id,
            payload.url,
        )

        # Calcula estimativa de tempo baseada no tipo de spider
        if payload.render_js:
            estimativa = "O job deve ser processado em até 120 segundos (renderização JS ativa)"
        elif payload.crawl_depth > 3:
            estimativa = f"O job deve ser processado em até {payload.crawl_depth * 60} segundos (crawling profundo)"
        else:
            estimativa = "O job deve ser processado em até 60 segundos"

        return JobCreatedResponse(
            job_id=job.id,
            status="pending",
            created_at=job.created_at,
            estimated_time=estimativa,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parâmetros inválidos: {str(exc)}",
        ) from exc
    except Exception as exc:
        logger.error("Erro ao criar job de scraping: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar o job de scraping. Tente novamente.",
        ) from exc


# ---------------------------------------------------------------------------
# POST /api/v1/scrape/bulk — Scraping em lote
# ---------------------------------------------------------------------------


@router.post(
    "/bulk",
    response_model=BulkJobCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Disparar scraping de múltiplas URLs",
    description="""
    Cria múltiplos jobs de scraping em lote (máximo 100 URLs por requisição).

    Cada URL recebe um job individual que é processado de forma independente.
    Use o endpoint `/api/v1/jobs` para listar e acompanhar os jobs criados.
    """,
    responses={
        201: {"description": "Jobs criados e enviados para processamento"},
        400: {"description": "URLs inválidas ou limite excedido"},
    },
)
@limiter.limit("5/minute")
async def criar_bulk_scrape(
    request: Request,
    payload: BulkScrapeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkJobCreatedResponse:
    """
    Dispara scraping de múltiplas URLs em lote.

    Args:
        request: Lista de URLs e configurações de scraping.
        db: Sessão do banco de dados.

    Returns:
        BulkJobCreatedResponse com IDs de todos os jobs criados.

    Raises:
        HTTPException 400: Se alguma URL for inválida.
        HTTPException 500: Se houver erro ao criar os jobs.
    """
    try:
        job_ids: list[int] = []

        # Cria um job para cada URL
        for url in payload.urls:
            job = await create_job(
                db,
                url=url,
                config_name=payload.config_name,
                spider_type=payload.spider_type,
                render_js=payload.render_js,
                crawl_depth=1,
                metadata=payload.metadata if payload.metadata else None,
            )
            job_ids.append(job.id)

        # Envia todas as tasks para o broker Celery
        task_ids = send_bulk_scrape_task(
            urls=payload.urls,
            job_ids=job_ids,
            config_name=payload.config_name,
            spider_type=payload.spider_type,
            render_js=payload.render_js,
            metadata=payload.metadata,
        )

        logger.info(
            "Bulk scrape disparado: %d jobs criados, task_ids=%s",
            len(job_ids),
            task_ids[:3],  # Loga apenas primeiros 3 IDs
        )

        return BulkJobCreatedResponse(
            job_ids=job_ids,
            total=len(job_ids),
            status="pending",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parâmetros inválidos: {str(exc)}",
        ) from exc
    except Exception as exc:
        logger.error("Erro ao criar jobs em lote: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar os jobs em lote. Tente novamente.",
        ) from exc


# ---------------------------------------------------------------------------
# POST /api/v1/scrape/preview — Preview sem salvar
# ---------------------------------------------------------------------------


@router.post(
    "/preview",
    response_model=PreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview de extração de dados",
    description="""
    Realiza uma extração de teste numa URL sem salvar os dados no banco.

    Útil para testar seletores CSS antes de criar uma configuração definitiva.
    O resultado retorna os dados extraídos, um trecho do HTML e o tempo gasto.

    **Nota:** O preview tem timeout de 30 segundos e não usa proxies.
    """,
    responses={
        200: {"description": "Preview realizado com sucesso"},
        400: {"description": "URL inválida ou inacessível"},
        408: {"description": "Timeout ao acessar a URL"},
    },
)
@limiter.limit("30/minute")
async def preview_scrape(
    request: Request,
    payload: PreviewRequest,
) -> PreviewResponse:
    """
    Realiza um preview de scraping sem persistir dados.

    Faz uma requisição HTTP à URL, aplica os seletores CSS fornecidos
    e retorna os dados extraídos junto com um trecho do HTML bruto.

    Args:
        request: URL, seletores CSS e configurações do preview.

    Returns:
        PreviewResponse com dados extraídos e HTML snippet.

    Raises:
        HTTPException 400: Se a URL for inválida.
        HTTPException 408: Se ocorrer timeout.
        HTTPException 502: Se a URL retornar erro HTTP.
    """
    inicio = time.perf_counter()

    try:
        # Realiza requisição HTTP com timeout de 30 segundos
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; WebScraper/1.0; Preview Mode)",
            },
        ) as client:
            response = await client.get(payload.url)

            if response.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"A URL retornou status {response.status_code}. Verifique se a URL está acessível.",
                )

            html_content = response.text

        # Aplica seletores CSS para extrair campos
        extracted_data: dict = {}

        if payload.selectors:
            try:
                # Usa BeautifulSoup se disponível, ou regex simples
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html_content, "html.parser")
                    for campo, seletor in payload.selectors.items():
                        elementos = soup.select(seletor)
                        if elementos:
                            # Extrai texto dos elementos encontrados
                            extracted_data[campo] = [el.get_text(strip=True) for el in elementos]
                            if len(extracted_data[campo]) == 1:
                                extracted_data[campo] = extracted_data[campo][0]
                        else:
                            extracted_data[campo] = None
                except ImportError:
                    # Fallback: extrai apenas título e meta description via regex
                    import re
                    titulo_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
                    extracted_data["titulo"] = titulo_match.group(1).strip() if titulo_match else None
                    extracted_data["aviso"] = "BeautifulSoup não disponível. Instale beautifulsoup4 para seletores CSS completos."

            except Exception as exc:
                logger.warning("Erro ao aplicar seletores CSS: %s", exc)
                extracted_data["erro_seletores"] = str(exc)

        else:
            # Sem seletores, extrai informações básicas
            import re
            titulo_match = re.search(r"<title[^>]*>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
            extracted_data["titulo"] = titulo_match.group(1).strip() if titulo_match else None
            extracted_data["tamanho_html"] = len(html_content)
            extracted_data["url_final"] = str(response.url)

        # Calcula tempo total em ms
        tempo_ms = (time.perf_counter() - inicio) * 1000

        # Prepara snippet do HTML (primeiros 2000 chars)
        html_snippet = html_content[:2000] if len(html_content) > 2000 else html_content

        logger.info(
            "Preview realizado: url=%s tempo=%.1fms campos=%d",
            payload.url,
            tempo_ms,
            len(extracted_data),
        )

        return PreviewResponse(
            extracted_data=extracted_data,
            raw_html_snippet=html_snippet,
            time_ms=round(tempo_ms, 2),
            url=str(response.url),
            success=True,
        )

    except httpx.TimeoutException as exc:
        tempo_ms = (time.perf_counter() - inicio) * 1000
        logger.warning("Timeout no preview da URL %s: %.1fms", payload.url, tempo_ms)
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Timeout ao acessar {payload.url}. A URL demorou mais de 30 segundos para responder.",
        ) from exc

    except httpx.RequestError as exc:
        logger.warning("Erro de conexão no preview da URL %s: %s", payload.url, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não foi possível acessar a URL: {str(exc)}",
        ) from exc

    except HTTPException:
        raise

    except Exception as exc:
        logger.error("Erro inesperado no preview: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno durante o preview. Tente novamente.",
        ) from exc
