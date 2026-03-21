"""
scheduler.py — Celery Beat Schedule para o WebScraper Jurídico

Define as tarefas periódicas automatizadas:
  - Atualização do pool de proxies (a cada 30 minutos)
  - Health check de proxies (a cada hora)
  - Limpeza de jobs antigos (diariamente às 3h)
  - Execução de agendamentos dinâmicos (a cada minuto)

Os agendamentos dinâmicos são lidos do banco de dados (tabela scheduled_jobs)
e permitem configurar execuções periódicas sem reiniciar o serviço.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

from celery.schedules import crontab

from .celery_config import app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração de banco de dados
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://scraper:scraper_pass_change_me@localhost:5432/webscraper",
)


# ---------------------------------------------------------------------------
# Celery Beat Schedule — agendamentos estáticos
# ---------------------------------------------------------------------------

app.conf.beat_schedule = {
    # ── Atualização do pool de proxies a cada 30 minutos ──────────────────
    "update-proxies": {
        "task": "worker.tasks.update_proxy_pool",
        "schedule": crontab(minute="*/30"),  # Ex: 00:00, 00:30, 01:00, ...
        "options": {
            "queue": "proxy_update",
            "routing_key": "proxy_update",
        },
    },

    # ── Health check dos proxies a cada hora ──────────────────────────────
    "health-check-proxies": {
        "task": "worker.tasks.health_check_proxies",
        "schedule": crontab(minute=0),  # No início de cada hora
        "options": {
            "queue": "proxy_update",
            "routing_key": "proxy_update",
        },
    },

    # ── Limpeza de jobs antigos diariamente às 3h da manhã ─────────────────
    "cleanup-old-jobs": {
        "task": "worker.tasks.cleanup_old_jobs",
        "schedule": crontab(hour=3, minute=0),  # 03:00 todos os dias
        "kwargs": {"days": 7},
        "options": {
            "queue": "maintenance",
            "routing_key": "maintenance",
        },
    },

    # ── Verificação e execução de agendamentos dinâmicos a cada minuto ────
    "dynamic-schedules": {
        "task": "worker.scheduler.run_dynamic_schedules",
        "schedule": crontab(minute="*"),  # Cada minuto
        "options": {
            "queue": "maintenance",
            "routing_key": "maintenance",
        },
    },
}


# ---------------------------------------------------------------------------
# Task: run_dynamic_schedules
# ---------------------------------------------------------------------------

@app.task(
    name="worker.scheduler.run_dynamic_schedules",
    bind=True,
    max_retries=1,
    soft_time_limit=55,   # Deve terminar antes do próximo ciclo (60s)
    time_limit=60,
    ignore_result=False,
)
def run_dynamic_schedules(self) -> dict[str, Any]:
    """
    Verifica e executa jobs agendados dinamicamente no banco de dados.

    Busca todos os ScheduledJob onde:
        - enabled = True
        - next_run <= now()

    Para cada job encontrado:
        1. Enfileira a task scrape_url correspondente
        2. Atualiza last_run e calcula next_run via croniter

    Returns:
        Dict com estatísticas: {verificados, disparados, erros}
    """
    logger.debug("[run_dynamic_schedules] Verificando agendamentos dinâmicos...")

    def _executar_sync() -> dict[str, Any]:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_verificar_e_disparar())
        finally:
            loop.close()

    async def _verificar_e_disparar() -> dict[str, Any]:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from database.models import ScheduledJob, SpiderConfig

        engine = create_async_engine(DATABASE_URL, pool_size=3, pool_pre_ping=True)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)

        estatisticas = {"verificados": 0, "disparados": 0, "erros": 0}
        agora = datetime.now(timezone.utc)

        try:
            async with factory() as session:
                # Busca jobs habilitados cujo next_run já passou
                result = await session.execute(
                    select(ScheduledJob)
                    .where(
                        ScheduledJob.enabled == True,  # noqa: E712
                        ScheduledJob.next_run <= agora,
                    )
                    .join(SpiderConfig)
                    .where(SpiderConfig.active == True)  # noqa: E712
                )
                jobs_pendentes = result.scalars().all()

                estatisticas["verificados"] = len(jobs_pendentes)

                for scheduled_job in jobs_pendentes:
                    try:
                        await _disparar_job_agendado(session, scheduled_job, agora)
                        estatisticas["disparados"] += 1

                    except Exception as exc:
                        logger.error(
                            "[run_dynamic_schedules] Erro ao disparar job agendado id=%d: %s",
                            scheduled_job.id,
                            exc,
                        )
                        estatisticas["erros"] += 1

                if jobs_pendentes:
                    await session.commit()

        except Exception as exc:
            logger.error("[run_dynamic_schedules] Erro ao consultar agendamentos: %s", exc)
            estatisticas["erros"] += 1
        finally:
            await engine.dispose()

        if estatisticas["disparados"] > 0:
            logger.info(
                "[run_dynamic_schedules] %d jobs disparados de %d verificados",
                estatisticas["disparados"],
                estatisticas["verificados"],
            )

        return estatisticas

    async def _disparar_job_agendado(session, scheduled_job: Any, agora: datetime) -> None:
        """
        Dispara a task de scraping para um ScheduledJob e atualiza next_run.

        Args:
            session:       Sessão SQLAlchemy ativa
            scheduled_job: Instância do ScheduledJob a executar
            agora:         Timestamp atual (evita chamadas múltiplas a now())
        """
        import yaml  # noqa: PLC0415
        from .tasks import scrape_url  # noqa: PLC0415

        # Carrega configuração do spider associado
        spider_config = scheduled_job.spider_config
        config: dict[str, Any] = {}

        if spider_config and spider_config.config_yaml:
            try:
                config = yaml.safe_load(spider_config.config_yaml) or {}
            except Exception as yaml_exc:
                logger.warning(
                    "YAML inválido na configuração '%s': %s",
                    spider_config.name,
                    yaml_exc,
                )

        # URL alvo vem da configuração do spider
        url = config.get("start_url", config.get("url", ""))

        if not url:
            logger.warning(
                "Job agendado id=%d sem URL configurada (config: %s)",
                scheduled_job.id,
                spider_config.name if spider_config else "N/A",
            )
            return

        # Cria um registro de job no banco para rastrear a execução
        from database.models import ScrapingJob, JobStatus  # noqa: PLC0415
        import json as _json  # noqa: PLC0415

        novo_job = ScrapingJob(
            url=url,
            config_name=spider_config.name if spider_config else None,
            status=JobStatus.PENDING.value,
            spider_type=spider_config.spider_type if spider_config else "generic",
            render_js=config.get("render_js", False),
            crawl_depth=config.get("crawl_depth", 1),
            metadata_={"triggered_by": f"scheduled_job:{scheduled_job.id}"},
        )
        session.add(novo_job)
        await session.flush()  # Obtém o ID sem commit

        # Enfileira a task de scraping
        scrape_url.apply_async(
            kwargs={
                "job_id": novo_job.id,
                "url": url,
                "spider_type": spider_config.spider_type if spider_config else "generic",
                "config_name": spider_config.name if spider_config else None,
                "render_js": config.get("render_js", False),
                "crawl_depth": config.get("crawl_depth", 1),
            },
            queue="scraping",
            routing_key="scraping",
        )

        # Atualiza last_run e calcula próxima execução via croniter
        proxima_execucao = _calcular_proxima_execucao(
            scheduled_job.cron_expression,
            agora,
        )

        scheduled_job.last_run = agora
        scheduled_job.next_run = proxima_execucao
        session.add(scheduled_job)

        logger.info(
            "[run_dynamic_schedules] Job agendado id=%d disparado: "
            "url=%s, novo_job_id=%d, próxima=%s",
            scheduled_job.id,
            url,
            novo_job.id,
            proxima_execucao.isoformat() if proxima_execucao else "N/A",
        )

    try:
        resultado = _executar_sync()
        return resultado

    except Exception as exc:
        logger.exception("[run_dynamic_schedules] Erro fatal: %s", exc)
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Utilitário: cálculo de próxima execução via croniter
# ---------------------------------------------------------------------------

def _calcular_proxima_execucao(
    cron_expression: str,
    base: datetime | None = None,
) -> datetime | None:
    """
    Calcula a próxima data/hora de execução a partir de uma expressão CRON.

    Usa a biblioteca croniter para parsing e cálculo preciso.

    Args:
        cron_expression: Expressão CRON (ex: '0 */6 * * *' = a cada 6 horas)
        base:            Ponto de referência para o cálculo (padrão: agora)

    Returns:
        Próxima data/hora de execução ou None em caso de expressão inválida.
    """
    try:
        from croniter import croniter  # noqa: PLC0415

        referencia = base or datetime.now(timezone.utc)

        # Normaliza timezone para comparação
        if referencia.tzinfo is None:
            referencia = referencia.replace(tzinfo=timezone.utc)

        iter_cron = croniter(cron_expression, referencia)
        proxima = iter_cron.get_next(datetime)

        # Garante que o resultado tem timezone UTC
        if proxima.tzinfo is None:
            proxima = proxima.replace(tzinfo=timezone.utc)

        return proxima

    except Exception as exc:
        logger.warning(
            "Expressão CRON inválida '%s': %s",
            cron_expression,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Utilitário: inicializa next_run de ScheduledJobs que ainda não têm valor
# ---------------------------------------------------------------------------

async def inicializar_proximas_execucoes() -> int:
    """
    Preenche o campo next_run de ScheduledJobs habilitados sem data calculada.

    Deve ser chamado durante o startup da aplicação para garantir que todos
    os agendamentos dinâmicos tenham next_run preenchido.

    Returns:
        Quantidade de registros atualizados.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from database.models import ScheduledJob

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    atualizados = 0
    agora = datetime.now(timezone.utc)

    try:
        async with factory() as session:
            result = await session.execute(
                select(ScheduledJob).where(
                    ScheduledJob.enabled == True,  # noqa: E712
                    ScheduledJob.next_run.is_(None),
                )
            )
            jobs_sem_next_run = result.scalars().all()

            for job in jobs_sem_next_run:
                proxima = _calcular_proxima_execucao(job.cron_expression, agora)
                if proxima:
                    job.next_run = proxima
                    session.add(job)
                    atualizados += 1

            if atualizados:
                await session.commit()
                logger.info(
                    "Inicializadas %d datas de próxima execução para ScheduledJobs",
                    atualizados,
                )

    finally:
        await engine.dispose()

    return atualizados
