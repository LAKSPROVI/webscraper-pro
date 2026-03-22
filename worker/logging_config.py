"""
logging_config.py — Configuração de logging JSON para workers Celery.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pythonjsonlogger import jsonlogger


class WorkerJsonFormatter(jsonlogger.JsonFormatter):
    """Formatter JSON com campos consistentes para observabilidade."""

    def add_fields(self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record.setdefault("level", record.levelname)
        log_record.setdefault("logger", record.name)
        log_record.setdefault("module", record.module)
        log_record.setdefault("function", record.funcName)
        log_record.setdefault("line", record.lineno)


def setup_worker_logging() -> None:
    """Configura root logger para saída JSON em stdout."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()

    # Evita handlers duplicados quando o módulo é importado múltiplas vezes.
    if getattr(root, "_worker_json_logging_configured", False):
        return

    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler()
    handler.setFormatter(
        WorkerJsonFormatter("%(asctime)s %(level)s %(name)s %(message)s")
    )
    root.addHandler(handler)

    root._worker_json_logging_configured = True  # type: ignore[attr-defined]
