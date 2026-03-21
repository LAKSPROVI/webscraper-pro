"""
__init__.py — Pacote de banco de dados do WebScraper Jurídico

Exporta os componentes principais para uso em toda a aplicação:
    - Models SQLAlchemy (ScrapingJob, ScrapedItem, SpiderConfig, etc.)
    - Engine, Session e dependências de conexão
    - Funções CRUD assíncronas
    - Enum de status do job
"""

from .connection import (
    AsyncSessionLocal,
    check_db,
    close_db,
    engine,
    get_db,
    get_session,
    init_db,
)
from .models import (
    Base,
    JobStatus,
    ProxyRecord,
    ScrapedItem,
    ScrapingJob,
    ScheduledJob,
    SpiderConfig,
)
from .queries import (
    count_items_by_domain,
    create_item,
    create_job,
    create_scheduled_job,
    create_spider_config,
    deduplicate_check,
    get_active_proxies,
    get_items_by_job,
    get_job,
    get_spider_config,
    list_active_scheduled_jobs,
    list_jobs,
    list_spider_configs,
    search_items,
    update_job_status,
    update_proxy_health,
    update_scheduled_job_run,
    upsert_proxy,
)

__all__ = [
    # ── Conexão ──────────────────────────────────────────────────────────────
    "engine",
    "AsyncSessionLocal",
    "get_db",
    "get_session",
    "init_db",
    "check_db",
    "close_db",
    # ── Base e Enum ───────────────────────────────────────────────────────────
    "Base",
    "JobStatus",
    # ── Models ────────────────────────────────────────────────────────────────
    "ScrapingJob",
    "ScrapedItem",
    "SpiderConfig",
    "ScheduledJob",
    "ProxyRecord",
    # ── Queries: ScrapingJob ──────────────────────────────────────────────────
    "create_job",
    "get_job",
    "update_job_status",
    "list_jobs",
    # ── Queries: ScrapedItem ──────────────────────────────────────────────────
    "create_item",
    "get_items_by_job",
    "search_items",
    "deduplicate_check",
    # ── Queries: SpiderConfig ─────────────────────────────────────────────────
    "create_spider_config",
    "get_spider_config",
    "list_spider_configs",
    # ── Queries: ScheduledJob ─────────────────────────────────────────────────
    "create_scheduled_job",
    "list_active_scheduled_jobs",
    "update_scheduled_job_run",
    # ── Queries: ProxyRecord ──────────────────────────────────────────────────
    "upsert_proxy",
    "get_active_proxies",
    "update_proxy_health",
    # ── Queries: Estatísticas ─────────────────────────────────────────────────
    "count_items_by_domain",
]
