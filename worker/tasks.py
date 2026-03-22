"""
tasks.py — Tasks Celery principais do WebScraper Jurídico

Tasks disponíveis:
  - scrape_url:          Executa scraping de uma URL específica
  - scrape_bulk:         Envia múltiplas URLs para scraping em paralelo
  - update_proxy_pool:   Atualiza o pool de proxies a partir de fontes externas
  - cleanup_old_jobs:    Remove jobs antigos do banco de dados
  - health_check_proxies: Verifica saúde dos proxies ativos

Todas as tasks possuem:
  - Retry automático com backoff exponencial
  - Tratamento robusto de erros
  - Logging estruturado
  - Publicação de eventos no Redis
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from celery import shared_task, chord, group
from celery.exceptions import SoftTimeLimitExceeded, MaxRetriesExceededError

from .celery_config import app
from .events import get_publisher
from .logging_config import setup_worker_logging

setup_worker_logging()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração de banco de dados (via variáveis de ambiente)
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://scraper:scraper_pass_change_me@localhost:5432/webscraper",
)


# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _run_async(coro) -> Any:
    """
    Executa uma coroutine async dentro de uma task Celery síncrona.

    Cria um novo event loop por thread para evitar conflitos com o
    loop do Celery/Twisted.

    Args:
        coro: Coroutine a executar

    Returns:
        Resultado da coroutine
    """
    # Usa loop dedicado por chamada para evitar conflitos com loops
    # internos de Twisted/Playwright/Scrapy em processos Celery.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()


async def _get_db_session():
    """Retorna uma sessão de banco de dados assíncrona."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=3)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    return factory, engine


# ---------------------------------------------------------------------------
# Task: scrape_url
# ---------------------------------------------------------------------------

@app.task(
    name="worker.tasks.scrape_url",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=300,
    time_limit=600,
)
def scrape_url(
    self,
    job_id: int,
    url: str,
    spider_type: str = "generic",
    config_name: str | None = None,
    render_js: bool = False,
    use_proxy: bool | None = None,
    crawl_depth: int = 1,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Executa o scraping de uma URL específica.

    Fluxo:
        1. Atualiza status do job para 'running' no PostgreSQL
        2. Publica evento 'job_started' no Redis
        3. Carrega configuração do spider (se config_name fornecido)
        4. Executa o spider via SpiderRunner
        5. Atualiza status para 'done' ou 'failed'
        6. Publica evento final no Redis

    Args:
        job_id:      ID do job a executar
        url:         URL alvo do scraping
        spider_type: Tipo do spider ('generic', 'js', 'rss', 'api', 'sitemap')
        config_name: Nome da configuração no banco (opcional)
        render_js:   Se deve renderizar JavaScript via Playwright
        crawl_depth: Profundidade máxima de crawling
        metadata:    Metadados extras para o spider

    Returns:
        Dict com resultado: {job_id, status, items_count, duration_seconds}
    """
    publisher = get_publisher()
    inicio = datetime.now(timezone.utc)

    logger.info(
        "[scrape_url] Iniciando job_id=%d, url=%s, spider=%s, render_js=%s",
        job_id,
        url,
        spider_type,
        render_js,
    )

    async def _preparar_execucao() -> dict[str, Any]:
        from sqlalchemy import select, update as sa_update
        from database.models import ScrapingJob, SpiderConfig, JobStatus

        factory, engine = await _get_db_session()

        try:
            async with factory() as session:
                # ── Passo 1: Atualiza status para 'running' ──────────────────
                await session.execute(
                    sa_update(ScrapingJob)
                    .where(ScrapingJob.id == job_id)
                    .values(
                        status=JobStatus.RUNNING.value,
                        started_at=inicio,
                    )
                )
                await session.commit()

                # ── Passo 2: Carrega configuração do spider ───────────────────
                config: dict[str, Any] = metadata or {}

                if config_name:
                    result = await session.execute(
                        select(SpiderConfig)
                        .where(SpiderConfig.name == config_name, SpiderConfig.active == True)  # noqa: E712
                    )
                    spider_config = result.scalar_one_or_none()

                    if spider_config:
                        import yaml  # noqa: PLC0415
                        yaml_config = yaml.safe_load(spider_config.config_yaml) or {}
                        config.update(yaml_config)
                        logger.debug(
                            "Configuração '%s' carregada para job_id=%d",
                            config_name,
                            job_id,
                        )
                    else:
                        logger.warning(
                            "Configuração '%s' não encontrada ou inativa para job_id=%d",
                            config_name,
                            job_id,
                        )

        finally:
            await engine.dispose()

        return {"config": config}

    try:
        preparo = _run_async(_preparar_execucao())
        config = preparo.get("config", {})

        # ── Passo 3: Publica evento de início ────────────────────────────
        publisher.job_started(
            job_id=job_id,
            url=url,
            worker_id=self.request.id,
        )

        # ── Passo 4: Executa o spider (fora do loop async) ───────────────
        from .spider_runner import SpiderRunner  # noqa: PLC0415

        runner = SpiderRunner()
        items_count = runner.run_spider(
            job_id=job_id,
            url=url,
            spider_type=spider_type,
            config=config,
            render_js=render_js,
            use_proxy=use_proxy,
            crawl_depth=crawl_depth,
        )

        async def _contar_itens_persistidos() -> int:
            from sqlalchemy import func, select
            from database.models import ScrapedItem

            factory, engine = await _get_db_session()
            try:
                async with factory() as session:
                    stmt = select(func.count(ScrapedItem.id)).where(ScrapedItem.job_id == job_id)
                    result = await session.execute(stmt)
                    return int(result.scalar() or 0)
            finally:
                await engine.dispose()

        persisted_items_count = _run_async(_contar_itens_persistidos())
        if persisted_items_count != items_count:
            logger.info(
                "[scrape_url] Ajustando items_count pelo banco: runner=%d persisted=%d job_id=%d",
                items_count,
                persisted_items_count,
                job_id,
            )
        items_count = persisted_items_count

        fim = datetime.now(timezone.utc)
        duracao = (fim - inicio).total_seconds()

        # ── Atualiza status para 'done' ──────────────────────────────────────
        async def _finalizar_sucesso() -> None:
            from sqlalchemy import update as sa_update
            from database.models import ScrapingJob, JobStatus

            factory, engine = await _get_db_session()
            try:
                async with factory() as session:
                    await session.execute(
                        sa_update(ScrapingJob)
                        .where(ScrapingJob.id == job_id)
                        .values(
                            status=JobStatus.DONE.value,
                            completed_at=fim,
                            items_scraped=items_count,
                        )
                    )
                    await session.commit()
            finally:
                await engine.dispose()

        _run_async(_finalizar_sucesso())

        # ── Publica evento de conclusão ──────────────────────────────────────
        publisher.job_done(
            job_id=job_id,
            items_count=items_count,
            duration_seconds=duracao,
        )

        logger.info(
            "[scrape_url] Concluído: job_id=%d, items=%d, duração=%.1fs",
            job_id,
            items_count,
            duracao,
        )

        return {
            "job_id": job_id,
            "status": "done",
            "items_count": items_count,
            "duration_seconds": round(duracao, 2),
        }

    except SoftTimeLimitExceeded:
        # Tempo suave excedido — atualiza status e re-raise
        _marcar_job_falhou(job_id, "Tempo limite de 5 minutos excedido")
        publisher.job_failed(
            job_id=job_id,
            error_msg="Tempo limite excedido (soft limit 5min)",
            error_type="SoftTimeLimitExceeded",
        )
        raise

    except TimeoutError as exc:
        erro = f"Spider excedeu timeout máximo: {exc}"
        logger.error("[scrape_url] Timeout job_id=%d: %s", job_id, exc)
        _marcar_job_falhou(job_id, erro)
        publisher.job_failed(job_id=job_id, error_msg=erro, error_type="TimeoutError")
        raise self.retry(exc=exc, countdown=_backoff(self.request.retries))

    except (ConnectionError, OSError) as exc:
        # Erros de rede → retry automático com backoff exponencial
        erro = f"Erro de rede: {exc}"
        logger.warning(
            "[scrape_url] Erro de rede (tentativa %d/%d): job_id=%d, %s",
            self.request.retries + 1,
            self.max_retries,
            job_id,
            exc,
        )
        raise self.retry(exc=exc, countdown=_backoff(self.request.retries))

    except Exception as exc:
        erro = f"{type(exc).__name__}: {exc}"
        logger.exception("[scrape_url] Erro fatal job_id=%d: %s", job_id, exc)
        _marcar_job_falhou(job_id, erro)
        publisher.job_failed(
            job_id=job_id,
            error_msg=erro,
            error_type=type(exc).__name__,
        )

        # Retry se ainda houver tentativas disponíveis
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=_backoff(self.request.retries))

        return {
            "job_id": job_id,
            "status": "failed",
            "error": erro,
        }


def _marcar_job_falhou(job_id: int, error_msg: str) -> None:
    """
    Atualiza o status do job para 'failed' no banco de dados.

    Args:
        job_id:    ID do job que falhou
        error_msg: Mensagem de erro descritiva
    """
    async def _atualizar() -> None:
        from sqlalchemy import update as sa_update
        from database.models import ScrapingJob, JobStatus

        factory, engine = await _get_db_session()
        try:
            async with factory() as session:
                await session.execute(
                    sa_update(ScrapingJob)
                    .where(ScrapingJob.id == job_id)
                    .values(
                        status=JobStatus.FAILED.value,
                        completed_at=datetime.now(timezone.utc),
                        error_msg=error_msg[:2000],  # Trunca mensagens muito longas
                    )
                )
                await session.commit()
        except Exception as db_exc:
            logger.error(
                "Falha ao marcar job %d como failed: %s",
                job_id,
                db_exc,
            )
        finally:
            await engine.dispose()

    try:
        _run_async(_atualizar())
    except Exception as exc:
        logger.error("Erro ao atualizar status de falha job_id=%d: %s", job_id, exc)


def _backoff(tentativa: int, base: int = 60, max_delay: int = 600) -> int:
    """
    Calcula delay com backoff exponencial para retries.

    Args:
        tentativa:  Número da tentativa atual (começa em 0)
        base:       Delay base em segundos (padrão: 60s)
        max_delay:  Delay máximo permitido (padrão: 10min)

    Returns:
        Delay em segundos para a próxima tentativa.
    """
    delay = min(base * (2 ** tentativa), max_delay)
    return delay


# ---------------------------------------------------------------------------
# Task: scrape_bulk
# ---------------------------------------------------------------------------

@app.task(
    name="worker.tasks.scrape_bulk",
    bind=True,
    max_retries=1,
    soft_time_limit=60,
    time_limit=120,
)
def scrape_bulk(
    self,
    job_ids_and_urls: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Enfileira múltiplas URLs para scraping em paralelo.

    Cada item na lista deve ter o formato:
        {
            "job_id": 123,
            "url": "https://...",
            "spider_type": "generic",  # opcional
            "config_name": "minha_config",  # opcional
            "render_js": False,  # opcional
            "crawl_depth": 1,  # opcional
            "metadata": {}  # opcional
        }

    Args:
        job_ids_and_urls: Lista de dicts com parâmetros de cada job

    Returns:
        Dict com IDs dos jobs enfileirados e contagem
    """
    logger.info(
        "[scrape_bulk] Enfileirando %d jobs para scraping",
        len(job_ids_and_urls),
    )

    jobs_enfileirados: list[str] = []
    erros: list[str] = []

    for item in job_ids_and_urls:
        try:
            job_id = item["job_id"]
            url = item["url"]

            # Parâmetros opcionais com defaults
            kwargs = {
                "job_id": job_id,
                "url": url,
                "spider_type": item.get("spider_type", "generic"),
                "config_name": item.get("config_name"),
                "render_js": item.get("render_js", False),
                "crawl_depth": item.get("crawl_depth", 1),
                "metadata": item.get("metadata"),
            }

            # Enfileira a task assíncrona
            task_result = scrape_url.apply_async(
                kwargs=kwargs,
                queue="scraping",
                routing_key="scraping",
            )

            jobs_enfileirados.append(task_result.id)

            logger.debug(
                "[scrape_bulk] Job enfileirado: job_id=%d, task_id=%s, url=%s",
                job_id,
                task_result.id,
                url,
            )

        except KeyError as exc:
            erro = f"Parâmetro obrigatório ausente: {exc}"
            logger.warning("[scrape_bulk] %s — item=%s", erro, item)
            erros.append(erro)

        except Exception as exc:
            erro = f"Falha ao enfileirar job_id={item.get('job_id', 'N/A')}: {exc}"
            logger.error("[scrape_bulk] %s", erro)
            erros.append(erro)

    resultado = {
        "total_solicitado": len(job_ids_and_urls),
        "enfileirados": len(jobs_enfileirados),
        "task_ids": jobs_enfileirados,
        "erros": erros,
    }

    logger.info(
        "[scrape_bulk] Concluído: %d/%d jobs enfileirados",
        len(jobs_enfileirados),
        len(job_ids_and_urls),
    )

    return resultado


# ---------------------------------------------------------------------------
# Task: update_proxy_pool
# ---------------------------------------------------------------------------

@app.task(
    name="worker.tasks.update_proxy_pool",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=600,
    time_limit=900,
    ignore_result=False,
)
def update_proxy_pool(self) -> dict[str, int]:
    """
    Atualiza o pool de proxies buscando de múltiplas fontes públicas.

    Fontes utilizadas:
        - ProxyScrape API
        - GitHub proxy-list (clarketm)
        - GitHub PROXY-List (TheSpeedX)
        - Geonode API pública

    Fluxo:
        1. Busca proxies de todas as fontes em paralelo
        2. Remove duplicatas
        3. Valida latência de cada proxy (máx 50 simultâneos)
        4. Salva proxies válidos no PostgreSQL
        5. Atualiza SET Redis 'active_proxies'

    Returns:
        Dict com estatísticas: {total_coletados, unicos, validos, salvos}
    """
    logger.info("[update_proxy_pool] Iniciando atualização do pool de proxies...")

    try:
        from .proxy_updater import ProxyUpdater  # noqa: PLC0415

        updater = ProxyUpdater()

        try:
            resultado = _run_async(updater.run_full_update())
        finally:
            _run_async(updater.close())

        logger.info(
            "[update_proxy_pool] Concluído: %d válidos de %d testados (%d salvos no DB)",
            resultado.get("validos", 0),
            resultado.get("unicos", 0),
            resultado.get("salvos", 0),
        )

        return resultado

    except Exception as exc:
        logger.exception("[update_proxy_pool] Erro durante atualização: %s", exc)
        raise self.retry(exc=exc, countdown=_backoff(self.request.retries, base=120))


# ---------------------------------------------------------------------------
# Task: cleanup_old_jobs
# ---------------------------------------------------------------------------

@app.task(
    name="worker.tasks.cleanup_old_jobs",
    bind=True,
    max_retries=1,
    soft_time_limit=300,
    time_limit=600,
    ignore_result=False,
)
def cleanup_old_jobs(self, days: int = 7) -> dict[str, int]:
    """
    Remove jobs concluídos mais antigos que N dias do banco de dados.

    Deleta em cascata os ScrapedItems associados aos jobs removidos
    (via CASCADE no banco de dados).

    Args:
        days: Número de dias de retenção (padrão: 7)

    Returns:
        Dict com contagens: {jobs_deletados, cutoff_date}
    """
    logger.info(
        "[cleanup_old_jobs] Iniciando limpeza de jobs com mais de %d dias...",
        days,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async def _limpar() -> dict[str, int]:
        from sqlalchemy import delete, select, func as sa_func
        from database.models import ScrapingJob, JobStatus

        factory, engine = await _get_db_session()

        try:
            async with factory() as session:
                # Conta quantos serão deletados antes de remover
                result_count = await session.execute(
                    sa_func.count(ScrapingJob.id)  # type: ignore[attr-defined]
                    if False  # Placeholder para sintaxe
                    else select(sa_func.count(ScrapingJob.id))
                    .where(
                        ScrapingJob.status == JobStatus.DONE.value,
                        ScrapingJob.completed_at < cutoff,
                    )
                )
                total_a_deletar = result_count.scalar() or 0

                # Realiza a deleção (items deletados em cascata pelo FK)
                resultado_delete = await session.execute(
                    delete(ScrapingJob).where(
                        ScrapingJob.status == JobStatus.DONE.value,
                        ScrapingJob.completed_at < cutoff,
                    )
                )

                jobs_deletados = resultado_delete.rowcount
                await session.commit()

                logger.info(
                    "[cleanup_old_jobs] Deletados %d jobs (>%d dias, cutoff=%s)",
                    jobs_deletados,
                    days,
                    cutoff.strftime("%Y-%m-%d"),
                )

                return {
                    "jobs_deletados": jobs_deletados,
                    "dias_retencao": days,
                    "cutoff_date": cutoff.isoformat(),
                }

        except Exception as exc:
            await session.rollback()
            raise
        finally:
            await engine.dispose()

    try:
        resultado = _run_async(_limpar())
        return resultado

    except Exception as exc:
        logger.exception("[cleanup_old_jobs] Erro durante limpeza: %s", exc)
        raise self.retry(exc=exc, countdown=300)


# ---------------------------------------------------------------------------
# Task: health_check_proxies
# ---------------------------------------------------------------------------

@app.task(
    name="worker.tasks.health_check_proxies",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    soft_time_limit=600,
    time_limit=900,
    ignore_result=False,
)
def health_check_proxies(self) -> dict[str, int]:
    """
    Re-verifica todos os proxies ativos e desativa os não funcionais.

    Critério de desativação:
        - Falha na verificação atual + success_rate < 50%

    Returns:
        Dict: {verificados, ativos, desativados}
    """
    logger.info("[health_check_proxies] Iniciando verificação de saúde dos proxies...")

    try:
        from .proxy_updater import ProxyUpdater  # noqa: PLC0415

        updater = ProxyUpdater()

        try:
            estatisticas = _run_async(updater.health_check_existing())
        finally:
            _run_async(updater.close())

        logger.info(
            "[health_check_proxies] Concluído: %d verificados, %d ativos, %d desativados",
            estatisticas.get("verificados", 0),
            estatisticas.get("ativos", 0),
            estatisticas.get("desativados", 0),
        )

        return estatisticas

    except Exception as exc:
        logger.exception("[health_check_proxies] Erro durante verificação: %s", exc)
        raise self.retry(exc=exc, countdown=_backoff(self.request.retries, base=120))
