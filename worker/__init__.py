"""
worker/__init__.py — Pacote de workers Celery do WebScraper Jurídico

Exporta os componentes principais para facilitar imports:
- app: instância Celery configurada
- tasks: tasks registradas
- EventPublisher: publicador de eventos Redis
"""

from .celery_config import app

__all__ = ["app"]
