import asyncio
import logging
import threading
from types import SimpleNamespace

import pytest

from backend.observability import (
    record_collector_duration,
    record_snmp_duration,
    request_timing_middleware,
)
from backend.snmp.client import _run_in_thread


class FakeRequest:
    method = "GET"
    scope = {"route": SimpleNamespace(path="/test/slow")}
    url = SimpleNamespace(path="/test/slow")

    def __init__(self, request_id: str | None = None):
        self.headers = {"X-Request-ID": request_id} if request_id else {}


class FakeResponse:
    status_code = 200


def test_slow_api_log_contains_canonical_timing_fields(caplog):
    async def slow_call(_request):
        await asyncio.sleep(0.51)
        return FakeResponse()

    with caplog.at_level(logging.WARNING, logger="backend.performance"):
        response = asyncio.run(
            request_timing_middleware(FakeRequest("req-123"), slow_call)
        )

    assert response.status_code == 200
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert message.startswith("slow_api ")
    assert "request_id=req-123" in message
    assert "total_ms=" in message
    assert "db_ms=0.0" in message
    assert "query_count=0" in message
    assert "snmp_ms=0.0" in message
    assert "collector_ms=0.0" in message


def test_request_id_is_generated_when_header_is_missing(caplog):
    async def fast_call(_request):
        return FakeResponse()

    with caplog.at_level(logging.INFO, logger="backend.performance"):
        asyncio.run(request_timing_middleware(FakeRequest(), fast_call))

    message = caplog.records[0].getMessage()
    assert message.startswith("api_request ")
    request_id = message.split("request_id=", 1)[1].split(" ", 1)[0]
    assert len(request_id) == 32
    assert "total_ms=" in message
    assert "db_ms=0.0" in message
    assert "query_count=0" in message
    assert "snmp_ms=0.0" in message
    assert "collector_ms=0.0" in message


def test_recorded_snmp_and_collector_times_are_logged(caplog):
    async def instrumented_call(_request):
        record_snmp_duration(12.5)
        record_collector_duration(3.5)
        return FakeResponse()

    with caplog.at_level(logging.INFO, logger="backend.performance"):
        asyncio.run(
            request_timing_middleware(FakeRequest("req-timing"), instrumented_call)
        )

    message = caplog.records[0].getMessage()
    assert "request_id=req-timing" in message
    assert "snmp_ms=12.5" in message
    assert "collector_ms=3.5" in message


def test_snmp_worker_cancels_coroutine_at_timeout():
    cancelled = threading.Event()

    async def never_finishes():
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    with pytest.raises(TimeoutError, match=r"SNMP operation timed out after 0\.1s"):
        _run_in_thread(never_finishes(), timeout=0.1)

    assert cancelled.is_set()
