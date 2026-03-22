from __future__ import annotations

import os
from typing import Any

import redis
from fastapi import APIRouter, HTTPException, status

from api.models.celery_app import send_proxy_health_check_task, send_update_proxy_pool_task

router = APIRouter(prefix="/api/v1/proxy", tags=["Proxy"])

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
PROXY_ENABLED_KEY = "proxy:enabled"
POOL_KEYS = ("active_proxies", "proxies:pool")


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


@router.get("/settings")
def get_proxy_settings() -> dict[str, Any]:
    redis_client: Any = redis.from_url(REDIS_URL, decode_responses=True)  # type: ignore
    try:
        enabled_raw = redis_client.get(PROXY_ENABLED_KEY)
        active_pool_size = redis_client.scard("active_proxies")
        legacy_pool_size = redis_client.scard("proxies:pool")
        ttl_active = redis_client.ttl("active_proxies")
        ttl_legacy = redis_client.ttl("proxies:pool")

        return {
            "enabled": _to_bool(enabled_raw, default=False),
            "enabled_raw": enabled_raw,
            "pool": {
                "active_proxies": {"size": active_pool_size, "ttl": ttl_active},
                "proxies_pool": {"size": legacy_pool_size, "ttl": ttl_legacy},
            },
        }
    finally:
        redis_client.close()


@router.post("/enable")
def enable_proxy() -> dict[str, Any]:
    redis_client: Any = redis.from_url(REDIS_URL, decode_responses=True)  # type: ignore
    try:
        redis_client.set(PROXY_ENABLED_KEY, "1")
        return {"enabled": True, "message": "Proxy global ativado"}
    finally:
        redis_client.close()


@router.post("/disable")
def disable_proxy() -> dict[str, Any]:
    redis_client: Any = redis.from_url(REDIS_URL, decode_responses=True)  # type: ignore
    try:
        redis_client.set(PROXY_ENABLED_KEY, "0")
        return {"enabled": False, "message": "Proxy global desativado"}
    finally:
        redis_client.close()


@router.post("/toggle")
def toggle_proxy() -> dict[str, Any]:
    redis_client: Any = redis.from_url(REDIS_URL, decode_responses=True)  # type: ignore
    try:
        current = _to_bool(redis_client.get(PROXY_ENABLED_KEY), default=False)
        new_value = not current
        redis_client.set(PROXY_ENABLED_KEY, "1" if new_value else "0")
        return {"enabled": new_value, "message": "Proxy global atualizado"}
    finally:
        redis_client.close()


@router.post("/pool/refresh")
async def refresh_proxy_pool() -> dict[str, Any]:
    try:
        task_id = send_update_proxy_pool_task()
        return {"queued": True, "task_id": task_id, "message": "Atualização do pool enfileirada"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao enfileirar atualização de proxies: {exc}",
        ) from exc


@router.post("/pool/health-check")
async def health_check_proxy_pool() -> dict[str, Any]:
    try:
        task_id = send_proxy_health_check_task()
        return {"queued": True, "task_id": task_id, "message": "Health check de proxies enfileirado"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao enfileirar health check de proxies: {exc}",
        ) from exc
