"""
queries.py — Operações CRUD assíncronas para o WebScraper Jurídico

Fornece funções de alto nível para criar, ler, atualizar e deletar
registros de todas as tabelas usando SQLAlchemy 2.0 com AsyncSession.

Organização:
    - ScrapingJob: create_job, get_job, update_job_status, list_jobs
    - ScrapedItem: create_item, get_items_by_job, search_items, deduplicate_check
    - SpiderConfig: create_spider_config, get_spider_config, list_spider_configs
    - ScheduledJob: create_scheduled_job, list_active_scheduled_jobs
    - ProxyRecord: upsert_proxy, get_active_proxies, update_proxy_health
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    JobStatus,
    ProxyRecord,
    ScrapedItem,
    ScrapingJob,
    ScheduledJob,
    SpiderConfig,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ScrapingJob — Operações de Job de Scraping
# =============================================================================


async def create_job(
    db: AsyncSession,
    url: str,
    *,
    config_name: Optional[str] = None,
    spider_type: Optional[str] = None,
    render_js: bool = False,
    crawl_depth: int = 1,
    metadata: Optional[dict[str, Any]] = None,
) -> ScrapingJob:
    """
    Cria um novo job de scraping no banco de dados.

    Args:
        db: Sessão assíncrona do banco de dados.
        url: URL alvo do scraping.
        config_name: Nome da configuração de spider (opcional).
        spider_type: Tipo do spider a utilizar.
        render_js: Se deve renderizar JavaScript.
        crawl_depth: Profundidade máxima de crawling.
        metadata: Metadados extras em formato JSON.

    Returns:
        Instância do ScrapingJob criado.
    """
    job = ScrapingJob(
        url=url,
        config_name=config_name,
        status=JobStatus.PENDING.value,
        spider_type=spider_type,
        render_js=render_js,
        crawl_depth=crawl_depth,
        metadata_=metadata,
    )
    db.add(job)
    await db.flush()  # Força geração do ID sem commit
    await db.refresh(job)
    logger.debug("Job criado: id=%s url=%s", job.id, url)
    return job


async def get_job(db: AsyncSession, job_id: int) -> Optional[ScrapingJob]:
    """
    Busca um job pelo seu ID.

    Args:
        db: Sessão assíncrona.
        job_id: ID do job a buscar.

    Returns:
        ScrapingJob se encontrado, None caso contrário.
    """
    result = await db.execute(select(ScrapingJob).where(ScrapingJob.id == job_id))
    return result.scalar_one_or_none()


async def update_job_status(
    db: AsyncSession,
    job_id: int,
    status: JobStatus,
    *,
    error_msg: Optional[str] = None,
    items_scraped: Optional[int] = None,
) -> Optional[ScrapingJob]:
    """
    Atualiza o status de um job e campos relacionados ao ciclo de vida.

    Gerencia automaticamente os timestamps:
    - RUNNING: preenche started_at
    - DONE / FAILED / CANCELLED: preenche completed_at

    Args:
        db: Sessão assíncrona.
        job_id: ID do job a atualizar.
        status: Novo status (JobStatus).
        error_msg: Mensagem de erro (apenas para status FAILED).
        items_scraped: Quantidade de itens coletados (para status DONE).

    Returns:
        ScrapingJob atualizado, ou None se não encontrado.
    """
    now = datetime.now(tz=timezone.utc)
    values: dict[str, Any] = {"status": status.value}

    if status == JobStatus.RUNNING:
        values["started_at"] = now
    elif status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
        values["completed_at"] = now

    if error_msg is not None:
        values["error_msg"] = error_msg

    if items_scraped is not None:
        values["items_scraped"] = items_scraped

    stmt = (
        update(ScrapingJob)
        .where(ScrapingJob.id == job_id)
        .values(**values)
        .returning(ScrapingJob)
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if job:
        logger.debug("Job %s atualizado para status=%s", job_id, status.value)
    return job


async def list_jobs(
    db: AsyncSession,
    *,
    status: Optional[JobStatus] = None,
    limit: int = 50,
    offset: int = 0,
    order_desc: bool = True,
) -> Sequence[ScrapingJob]:
    """
    Lista jobs com filtro opcional de status e paginação.

    Args:
        db: Sessão assíncrona.
        status: Filtrar por status específico (opcional).
        limit: Máximo de resultados.
        offset: Posição inicial para paginação.
        order_desc: Se True, ordena do mais recente para o mais antigo.

    Returns:
        Sequência de ScrapingJob.
    """
    stmt = select(ScrapingJob)

    if status is not None:
        stmt = stmt.where(ScrapingJob.status == status.value)

    if order_desc:
        stmt = stmt.order_by(ScrapingJob.created_at.desc())
    else:
        stmt = stmt.order_by(ScrapingJob.created_at.asc())

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


# =============================================================================
# ScrapedItem — Operações de Itens Coletados
# =============================================================================


async def deduplicate_check(db: AsyncSession, content_hash: str) -> bool:
    """
    Verifica se um item com o mesmo hash já existe no banco.

    Args:
        db: Sessão assíncrona.
        content_hash: Hash SHA-256 do conteúdo a verificar.

    Returns:
        True se o item já existe (duplicado), False caso contrário.
    """
    stmt = select(ScrapedItem.id).where(ScrapedItem.content_hash == content_hash).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def create_item(
    db: AsyncSession,
    job_id: int,
    url: str,
    content: str,
    *,
    title: Optional[str] = None,
    raw_data: Optional[dict[str, Any]] = None,
    domain: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    skip_duplicate: bool = True,
) -> Optional[ScrapedItem]:
    """
    Cria um novo item coletado, com verificação opcional de duplicatas.

    Calcula automaticamente o hash SHA-256 do conteúdo para deduplicação.

    Args:
        db: Sessão assíncrona.
        job_id: ID do job que gerou este item.
        url: URL de onde o item foi coletado.
        content: Conteúdo textual extraído.
        title: Título da página/item (opcional).
        raw_data: Dados brutos em JSON (opcional).
        domain: Domínio extraído da URL (opcional).
        metadata: Metadados adicionais (opcional).
        skip_duplicate: Se True, não cria item se hash já existir.

    Returns:
        ScrapedItem criado, ou None se for duplicata e skip_duplicate=True.
    """
    content_hash = ScrapedItem.compute_hash(content)

    if skip_duplicate:
        is_dup = await deduplicate_check(db, content_hash)
        if is_dup:
            logger.debug("Item duplicado ignorado: hash=%s url=%s", content_hash[:8], url)
            return None

    item = ScrapedItem(
        job_id=job_id,
        url=url,
        title=title,
        content=content,
        raw_data=raw_data,
        content_hash=content_hash,
        domain=domain,
        metadata_=metadata,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    logger.debug("Item criado: id=%s job_id=%s domain=%s", item.id, job_id, domain)
    return item


async def get_items_by_job(
    db: AsyncSession,
    job_id: int,
    *,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[ScrapedItem]:
    """
    Retorna todos os itens coletados de um job específico.

    Args:
        db: Sessão assíncrona.
        job_id: ID do job.
        limit: Máximo de resultados.
        offset: Posição inicial para paginação.

    Returns:
        Sequência de ScrapedItem do job.
    """
    stmt = (
        select(ScrapedItem)
        .where(ScrapedItem.job_id == job_id)
        .order_by(ScrapedItem.scraped_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def search_items(
    db: AsyncSession,
    query: str,
    *,
    domain: Optional[str] = None,
    job_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[ScrapedItem]:
    """
    Busca textual nos itens coletados por título e conteúdo.

    Args:
        db: Sessão assíncrona.
        query: Texto a buscar (busca parcial case-insensitive).
        domain: Filtrar por domínio específico (opcional).
        job_id: Filtrar por job específico (opcional).
        limit: Máximo de resultados.
        offset: Posição inicial para paginação.

    Returns:
        Sequência de ScrapedItem correspondentes à busca.
    """
    like_pattern = f"%{query}%"
    stmt = select(ScrapedItem).where(
        or_(
            ScrapedItem.title.ilike(like_pattern),
            ScrapedItem.content.ilike(like_pattern),
        )
    )

    if domain is not None:
        stmt = stmt.where(ScrapedItem.domain == domain)

    if job_id is not None:
        stmt = stmt.where(ScrapedItem.job_id == job_id)

    stmt = (
        stmt.order_by(ScrapedItem.scraped_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# =============================================================================
# SpiderConfig — Operações de Configuração de Spider
# =============================================================================


async def create_spider_config(
    db: AsyncSession,
    name: str,
    config_yaml: str,
    *,
    spider_type: Optional[str] = None,
    description: Optional[str] = None,
    active: bool = True,
) -> SpiderConfig:
    """
    Cria uma nova configuração de spider.

    Args:
        db: Sessão assíncrona.
        name: Nome único da configuração.
        config_yaml: Configuração em formato YAML.
        spider_type: Tipo do spider.
        description: Descrição legível.
        active: Se a configuração está ativa.

    Returns:
        SpiderConfig criada.

    Raises:
        IntegrityError: Se já existe uma configuração com o mesmo nome.
    """
    config = SpiderConfig(
        name=name,
        config_yaml=config_yaml,
        spider_type=spider_type,
        description=description,
        active=active,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config)
    logger.debug("SpiderConfig criada: id=%s name=%s", config.id, name)
    return config


async def get_spider_config(
    db: AsyncSession,
    config_id: Optional[int] = None,
    name: Optional[str] = None,
) -> Optional[SpiderConfig]:
    """
    Busca uma configuração de spider por ID ou nome.

    Args:
        db: Sessão assíncrona.
        config_id: ID da configuração (opcional).
        name: Nome da configuração (opcional).

    Returns:
        SpiderConfig se encontrada, None caso contrário.

    Raises:
        ValueError: Se nenhum critério de busca for fornecido.
    """
    if config_id is None and name is None:
        raise ValueError("Forneça config_id ou name para buscar a configuração.")

    stmt = select(SpiderConfig)
    if config_id is not None:
        stmt = stmt.where(SpiderConfig.id == config_id)
    elif name is not None:
        stmt = stmt.where(SpiderConfig.name == name)

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_spider_configs(
    db: AsyncSession,
    *,
    active_only: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[SpiderConfig]:
    """
    Lista todas as configurações de spider.

    Args:
        db: Sessão assíncrona.
        active_only: Se True, retorna apenas configurações ativas.
        limit: Máximo de resultados.
        offset: Posição inicial para paginação.

    Returns:
        Sequência de SpiderConfig.
    """
    stmt = select(SpiderConfig)
    if active_only:
        stmt = stmt.where(SpiderConfig.active.is_(True))
    stmt = stmt.order_by(SpiderConfig.name.asc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


# =============================================================================
# ScheduledJob — Operações de Jobs Agendados
# =============================================================================


async def create_scheduled_job(
    db: AsyncSession,
    name: str,
    spider_config_id: int,
    cron_expression: str,
    *,
    enabled: bool = True,
    next_run: Optional[datetime] = None,
) -> ScheduledJob:
    """
    Cria um novo job agendado com expressão CRON.

    Args:
        db: Sessão assíncrona.
        name: Nome descritivo do agendamento.
        spider_config_id: ID da configuração do spider a usar.
        cron_expression: Expressão CRON (ex: '0 */6 * * *').
        enabled: Se o agendamento está habilitado desde a criação.
        next_run: Data/hora da próxima execução (calculada externamente).

    Returns:
        ScheduledJob criado.
    """
    job = ScheduledJob(
        name=name,
        spider_config_id=spider_config_id,
        cron_expression=cron_expression,
        enabled=enabled,
        next_run=next_run,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    logger.debug("ScheduledJob criado: id=%s name=%s cron=%s", job.id, name, cron_expression)
    return job


async def list_active_scheduled_jobs(
    db: AsyncSession,
    *,
    due_before: Optional[datetime] = None,
) -> Sequence[ScheduledJob]:
    """
    Lista os jobs agendados habilitados e prontos para execução.

    Args:
        db: Sessão assíncrona.
        due_before: Se informado, filtra jobs com next_run <= due_before.
                    Útil para o scheduler verificar quais jobs devem rodar agora.

    Returns:
        Sequência de ScheduledJob prontos para execução.
    """
    stmt = select(ScheduledJob).where(ScheduledJob.enabled.is_(True))

    if due_before is not None:
        stmt = stmt.where(
            or_(
                ScheduledJob.next_run.is_(None),
                ScheduledJob.next_run <= due_before,
            )
        )

    stmt = stmt.order_by(ScheduledJob.next_run.asc().nulls_first())
    result = await db.execute(stmt)
    return result.scalars().all()


async def update_scheduled_job_run(
    db: AsyncSession,
    job_id: int,
    *,
    last_run: datetime,
    next_run: Optional[datetime] = None,
) -> Optional[ScheduledJob]:
    """
    Atualiza os timestamps de last_run e next_run após execução.

    Args:
        db: Sessão assíncrona.
        job_id: ID do job agendado.
        last_run: Timestamp da execução atual.
        next_run: Timestamp calculado da próxima execução.

    Returns:
        ScheduledJob atualizado, ou None se não encontrado.
    """
    values: dict[str, Any] = {"last_run": last_run}
    if next_run is not None:
        values["next_run"] = next_run

    stmt = (
        update(ScheduledJob)
        .where(ScheduledJob.id == job_id)
        .values(**values)
        .returning(ScheduledJob)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# =============================================================================
# ProxyRecord — Operações de Proxies
# =============================================================================


async def upsert_proxy(
    db: AsyncSession,
    host: str,
    port: int,
    *,
    protocol: str = "http",
    country: Optional[str] = None,
    latency_ms: Optional[float] = None,
    success_rate: float = 1.0,
    active: bool = True,
) -> ProxyRecord:
    """
    Insere ou atualiza um proxy no banco (upsert por host+port+protocol).

    Args:
        db: Sessão assíncrona.
        host: Host ou IP do proxy.
        port: Porta do proxy.
        protocol: Protocolo (http, https, socks5).
        country: Código do país ISO (ex: BR).
        latency_ms: Latência medida em ms.
        success_rate: Taxa de sucesso (0.0 a 1.0).
        active: Se o proxy está ativo.

    Returns:
        ProxyRecord inserido ou atualizado.
    """
    now = datetime.now(tz=timezone.utc)

    # Usa INSERT ... ON CONFLICT para upsert eficiente no PostgreSQL
    stmt = (
        pg_insert(ProxyRecord)
        .values(
            host=host,
            port=port,
            protocol=protocol,
            country=country,
            latency_ms=latency_ms,
            success_rate=success_rate,
            last_checked=now,
            active=active,
        )
        .on_conflict_do_update(
            # Índice único composto (host, port, protocol)
            # Deve ser criado na migration
            index_elements=["host", "port", "protocol"],
            set_={
                "country": country,
                "latency_ms": latency_ms,
                "success_rate": success_rate,
                "last_checked": now,
                "active": active,
            },
        )
        .returning(ProxyRecord)
    )
    result = await db.execute(stmt)
    proxy = result.scalar_one()
    logger.debug(
        "Proxy upsert: %s://%s:%s active=%s latency=%s ms",
        protocol, host, port, active, latency_ms,
    )
    return proxy


async def get_active_proxies(
    db: AsyncSession,
    *,
    protocol: Optional[str] = None,
    country: Optional[str] = None,
    min_success_rate: float = 0.5,
    limit: int = 50,
) -> Sequence[ProxyRecord]:
    """
    Retorna proxies ativos ordenados por menor latência e maior sucesso.

    Args:
        db: Sessão assíncrona.
        protocol: Filtrar por protocolo específico (opcional).
        country: Filtrar por país (opcional).
        min_success_rate: Taxa mínima de sucesso (padrão: 50%).
        limit: Máximo de proxies a retornar.

    Returns:
        Sequência de ProxyRecord ordenada por qualidade.
    """
    stmt = select(ProxyRecord).where(
        ProxyRecord.active.is_(True),
        ProxyRecord.success_rate >= min_success_rate,
    )

    if protocol is not None:
        stmt = stmt.where(ProxyRecord.protocol == protocol)

    if country is not None:
        stmt = stmt.where(ProxyRecord.country == country)

    # Ordena por taxa de sucesso decrescente, latência crescente
    stmt = stmt.order_by(
        ProxyRecord.success_rate.desc(),
        ProxyRecord.latency_ms.asc().nulls_last(),
    ).limit(limit)

    result = await db.execute(stmt)
    return result.scalars().all()


async def update_proxy_health(
    db: AsyncSession,
    proxy_id: int,
    *,
    latency_ms: Optional[float],
    success: bool,
) -> Optional[ProxyRecord]:
    """
    Atualiza os dados de saúde de um proxy após tentativa de uso.

    Calcula a nova taxa de sucesso usando média móvel exponencial (EMA)
    com fator de suavização 0.2 (20% do novo resultado, 80% do histórico).

    Args:
        db: Sessão assíncrona.
        proxy_id: ID do proxy a atualizar.
        latency_ms: Nova latência medida (None se falhou).
        success: Se a última requisição via este proxy foi bem-sucedida.

    Returns:
        ProxyRecord atualizado, ou None se não encontrado.
    """
    proxy = await db.get(ProxyRecord, proxy_id)
    if proxy is None:
        return None

    # Fator de suavização para EMA (alpha = 0.2)
    alpha = 0.2
    new_sample = 1.0 if success else 0.0
    proxy.success_rate = (alpha * new_sample) + ((1 - alpha) * (proxy.success_rate or 1.0))
    proxy.latency_ms = latency_ms
    proxy.last_checked = datetime.now(tz=timezone.utc)

    # Desativa proxy com taxa de sucesso muito baixa
    if proxy.success_rate < 0.1:
        proxy.active = False
        logger.warning("Proxy %s desativado por baixa taxa de sucesso (%.2f)", proxy_id, proxy.success_rate)

    await db.flush()
    return proxy


# =============================================================================
# Utilidades de estatísticas
# =============================================================================


async def count_items_by_domain(
    db: AsyncSession,
    job_id: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Conta itens coletados agrupados por domínio.

    Args:
        db: Sessão assíncrona.
        job_id: Filtrar por job específico (opcional).

    Returns:
        Lista de dicts com 'domain' e 'count'.
    """
    stmt = select(ScrapedItem.domain, func.count(ScrapedItem.id).label("count")).group_by(
        ScrapedItem.domain
    )

    if job_id is not None:
        stmt = stmt.where(ScrapedItem.job_id == job_id)

    stmt = stmt.order_by(func.count(ScrapedItem.id).desc())
    result = await db.execute(stmt)
    return [{"domain": row.domain, "count": row.count} for row in result]
