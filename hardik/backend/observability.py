"""Lightweight request and backend operation timing instrumentation."""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

from sqlalchemy import event

logger = logging.getLogger("backend.performance")

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
db_duration_var: ContextVar[float] = ContextVar("db_duration_ms", default=0.0)
db_query_count_var: ContextVar[int] = ContextVar("db_query_count", default=0)
snmp_duration_var: ContextVar[float] = ContextVar("snmp_duration_ms", default=0.0)
collector_duration_var: ContextVar[float] = ContextVar("collector_duration_ms", default=0.0)
timing_state_var: ContextVar[dict[str, Any] | None] = ContextVar("timing_state", default=None)


def _add_duration(var: ContextVar[float], duration_ms: float) -> None:
    var.set(var.get() + duration_ms)


def _add_to_request_state(key: str, value: float) -> None:
    state = timing_state_var.get()
    if state is not None:
        state[key] = state.get(key, 0.0) + value


def record_snmp_duration(duration_ms: float) -> None:
    _add_duration(snmp_duration_var, duration_ms)
    _add_to_request_state("snmp_ms", duration_ms)


def record_collector_duration(duration_ms: float) -> None:
    _add_duration(collector_duration_var, duration_ms)
    _add_to_request_state("collector_ms", duration_ms)


def install_db_timing(engine: Any) -> None:
    """Attach SQLAlchemy timing listeners once, without changing query behavior."""
    if getattr(engine, "_nms_timing_installed", False):
        return

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        context._nms_query_started = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool) -> None:
        started = getattr(context, "_nms_query_started", None)
        if started is None:
            return
        duration_ms = (time.perf_counter() - started) * 1000
        db_duration_var.set(db_duration_var.get() + duration_ms)
        db_query_count_var.set(db_query_count_var.get() + 1)
        state = timing_state_var.get()
        if state is not None:
            state["db_ms"] = state.get("db_ms", 0.0) + duration_ms
            state["query_count"] = state.get("query_count", 0) + 1

    engine._nms_timing_installed = True


async def request_timing_middleware(request: Any, call_next: Any) -> Any:
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request_token = request_id_var.set(request_id)
    db_token = db_duration_var.set(0.0)
    count_token = db_query_count_var.set(0)
    snmp_token = snmp_duration_var.set(0.0)
    collector_token = collector_duration_var.set(0.0)
    timing_state = {"db_ms": 0.0, "query_count": 0,
                    "snmp_ms": 0.0, "collector_ms": 0.0}
    state_token = timing_state_var.set(timing_state)
    started = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        total_duration_ms = round((time.perf_counter() - started) * 1000, 1)
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or request.url.path
        fields = (
            "request_id=%s method=%s route=%s status_code=%s "
            "total_ms=%.1f db_ms=%.1f query_count=%s "
            "snmp_ms=%.1f collector_ms=%.1f"
        )
        values = (
            request_id,
            request.method,
            route_path,
            status_code,
            total_duration_ms,
            timing_state["db_ms"],
            timing_state["query_count"],
            timing_state["snmp_ms"],
            timing_state["collector_ms"],
        )
        if total_duration_ms > 500:
            logger.warning("slow_api " + fields, *values)
        else:
            logger.info("api_request " + fields, *values)

        request_id_var.reset(request_token)
        db_duration_var.reset(db_token)
        db_query_count_var.reset(count_token)
        snmp_duration_var.reset(snmp_token)
        collector_duration_var.reset(collector_token)
        timing_state_var.reset(state_token)
