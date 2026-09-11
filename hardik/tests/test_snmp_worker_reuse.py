from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from backend.snmp import client as client_module


class _Engine:
    def __init__(self, created, closed):
        created.append(self)
        self.transportDispatcher = SimpleNamespace(
            closeDispatcher=lambda: closed.append(self)
        )


def _install_engine(monkeypatch):
    import pysnmp.hlapi.asyncio as hlapi
    created = []
    closed = []
    monkeypatch.setattr(hlapi, "SnmpEngine", lambda: _Engine(created, closed))
    return created, closed


async def _runtime_identity():
    loop = asyncio.get_running_loop()
    engine = client_module._worker_engine.get()
    return id(loop), id(engine), threading.get_ident()


def test_same_worker_reuses_loop_and_engine(monkeypatch):
    created, closed = _install_engine(monkeypatch)
    pool = client_module.SNMPWorkerPool(workers=1)
    try:
        first = pool.submit(_runtime_identity(), 1)
        second = pool.submit(_runtime_identity(), 1)
        assert first == second
        assert len(created) == 1
    finally:
        pool.shutdown()
    assert closed == created


def test_different_workers_own_distinct_runtime_state(monkeypatch):
    created, closed = _install_engine(monkeypatch)
    pool = client_module.SNMPWorkerPool(workers=2)
    try:
        first = pool.submit(_runtime_identity(), 1)
        second = pool.submit(_runtime_identity(), 1)
        assert first[0] != second[0]
        assert first[1] != second[1]
        assert first[2] != second[2]
    finally:
        pool.shutdown()
    assert len(created) == len(closed) == 2


def test_failed_operation_does_not_poison_worker(monkeypatch):
    created, _closed = _install_engine(monkeypatch)
    pool = client_module.SNMPWorkerPool(workers=1)

    async def fail():
        raise ValueError("request failed")

    try:
        with pytest.raises(ValueError, match="request failed"):
            pool.submit(fail(), 1)
        assert pool.submit(_runtime_identity(), 1)[1] == id(created[0])
    finally:
        pool.shutdown()


def test_runtime_failure_recreates_only_affected_worker(monkeypatch):
    created, closed = _install_engine(monkeypatch)
    pool = client_module.SNMPWorkerPool(workers=1)

    async def fail_runtime():
        raise RuntimeError("runtime unusable")

    try:
        with pytest.raises(RuntimeError, match="runtime unusable"):
            pool.submit(fail_runtime(), 1)
        recovered = pool.submit(_runtime_identity(), 1)
        assert len(created) == 2
        assert recovered[1] == id(created[1])
        assert created[0] in closed
    finally:
        pool.shutdown()


def test_shutdown_rejects_new_work_without_coroutine_leak(monkeypatch):
    _install_engine(monkeypatch)
    pool = client_module.SNMPWorkerPool(workers=1)
    pool.submit(_runtime_identity(), 1)
    pool.shutdown()
    coro = _runtime_identity()
    with pytest.raises(RuntimeError, match="shut down"):
        pool.submit(coro, 1)
    assert all(not worker.thread.is_alive() for worker in pool._workers)
