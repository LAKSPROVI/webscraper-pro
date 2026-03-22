"""
rate_limiter.py — Configuração centralizada de rate limiting para FastAPI.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Limite padrão para endpoints sem decorator explícito.
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
