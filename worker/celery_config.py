"""
celery_config.py — Configuração completa do Celery para o WebScraper Jurídico

Configura:
- App Celery com nome 'webscraper'
- Broker e backend Redis
- Filas de tasks (default, scraping, proxy_update, maintenance)
- Roteamento automático de tasks por prefixo de nome
- Limites de tempo, retries e serialização segura
- Timezone América/São Paulo
"""

from __future__ import annotations

import logging
import os

from celery import Celery
from kombu import Exchange, Queue

from .logging_config import setup_worker_logging

setup_worker_logging()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Variáveis de ambiente
# ---------------------------------------------------------------------------

CELERY_BROKER_URL: str = os.getenv(
    "CELERY_BROKER_URL", "redis://localhost:6379/0"
)
CELERY_RESULT_BACKEND: str = os.getenv(
    "CELERY_RESULT_BACKEND", "redis://localhost:6379/1"
)

# ---------------------------------------------------------------------------
# Criação da aplicação Celery
# ---------------------------------------------------------------------------

app = Celery("webscraper")

# ---------------------------------------------------------------------------
# Exchanges e Queues
# ---------------------------------------------------------------------------

# Exchange padrão (direct)
default_exchange = Exchange("default", type="direct")
scraping_exchange = Exchange("scraping", type="direct")
proxy_exchange = Exchange("proxy_update", type="direct")
maintenance_exchange = Exchange("maintenance", type="direct")

TASK_QUEUES = (
    Queue("default",      default_exchange,     routing_key="default"),
    Queue("scraping",     scraping_exchange,     routing_key="scraping"),
    Queue("proxy_update", proxy_exchange,        routing_key="proxy_update"),
    Queue("maintenance",  maintenance_exchange,  routing_key="maintenance"),
)

# ---------------------------------------------------------------------------
# Roteamento automático de tasks
# ---------------------------------------------------------------------------

TASK_ROUTES = {
    # Tasks de scraping → fila scraping
    "worker.tasks.scrape_url":   {"queue": "scraping",     "routing_key": "scraping"},
    "worker.tasks.scrape_bulk":  {"queue": "scraping",     "routing_key": "scraping"},
    # Tasks de proxy → fila proxy_update
    "worker.tasks.update_proxy_pool":    {"queue": "proxy_update", "routing_key": "proxy_update"},
    "worker.tasks.health_check_proxies": {"queue": "proxy_update", "routing_key": "proxy_update"},
    # Tasks de manutenção → fila maintenance
    "worker.tasks.cleanup_old_jobs":     {"queue": "maintenance",  "routing_key": "maintenance"},
    "worker.scheduler.run_dynamic_schedules": {"queue": "maintenance", "routing_key": "maintenance"},
}

# ---------------------------------------------------------------------------
# Aplicação das configurações via update_config
# ---------------------------------------------------------------------------

app.conf.update(
    # ── Broker e backend ────────────────────────────────────────────────────
    broker_url=CELERY_BROKER_URL,
    result_backend=CELERY_RESULT_BACKEND,

    # ── Serialização segura ─────────────────────────────────��────────────────
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # ── Filas e roteamento ───────────────────────────────────────────────────
    task_queues=TASK_QUEUES,
    task_routes=TASK_ROUTES,
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",

    # ── Limites de tempo por task ────────────────────────────────────────────
    task_soft_time_limit=300,   # 5 minutos: lança SoftTimeLimitExceeded
    task_time_limit=600,        # 10 minutos: força kill do processo

    # ── Retry automático ─────────────────────────────────────────────────────
    task_max_retries=3,
    task_default_retry_delay=60,  # Delay inicial de 1 minuto (backoff exponencial nas tasks)

    # ── Prefetch: 1 para tasks pesadas (evita acúmulo em workers) ───────────
    worker_prefetch_multiplier=1,

    # ── Expiração dos resultados ─────────────────────────────────────────────
    result_expires=86400,  # 24 horas

    # ── Timezone ──────────────────────────────────────────────────────────────
    timezone="America/Sao_Paulo",
    enable_utc=True,

    # ── Autodiscovery de tasks ────────────────────────────────────────────────
    imports=["worker.tasks", "worker.scheduler"],

    # ── Configurações de worker ──────────────────────────────────────────────
    worker_max_tasks_per_child=100,    # Reinicia worker a cada 100 tasks (evita memory leaks)
    worker_max_memory_per_child=500000, # 500MB por processo worker

    # ── Monitoramento de eventos (Flower) ────────────────────────────────────
    worker_send_task_events=True,
    task_send_sent_event=True,

    # ── Acks após execução (previne perda de tasks em crash) ─────────────────
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # ── Compressão de resultados grandes ─────────────────────────────────────
    result_compression="gzip",

    # ── Broker connection retry ───────────────────────────────────────────────
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_connection_retry_delay=5.0,

    # ── Configurações de Beat (scheduler) ────────────────────────────────────
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename="/tmp/celerybeat-schedule",
)

logger.info(
    "Celery configurado: broker=%s, result_backend=%s",
    CELERY_BROKER_URL.split("@")[-1],  # Omite credenciais no log
    CELERY_RESULT_BACKEND.split("@")[-1],
)
