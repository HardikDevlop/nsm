"""Small fail-open Redis cache-aside helper for selected read APIs."""

from __future__ import annotations

import json
import logging
from threading import Lock
from typing import Any

from backend.config.settings import get_settings

logger = logging.getLogger(__name__)

_client: Any | None = None
_client_lock = Lock()


def _get_client() -> Any | None:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        try:
            import redis

            settings = get_settings()
            _client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
            )
        except Exception as exc:
            logger.debug("redis_cache_unavailable reason=%s", exc)
            return None
    return _client


def get_json(key: str) -> Any | None:
    client = _get_client()
    if client is None:
        return None
    try:
        value = client.get(key)
        return json.loads(value) if value is not None else None
    except Exception as exc:
        logger.debug("redis_cache_read_failed key=%s reason=%s", key, exc)
        return None


def set_json(key: str, value: Any, ttl_seconds: int | None = None) -> bool:
    client = _get_client()
    if client is None:
        return False
    try:
        ttl = ttl_seconds if ttl_seconds is not None else get_settings().redis_cache_ttl_seconds
        client.setex(key, max(1, int(ttl)), json.dumps(value, separators=(",", ":")))
        return True
    except Exception as exc:
        logger.debug("redis_cache_write_failed key=%s reason=%s", key, exc)
        return False
