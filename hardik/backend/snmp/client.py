"""
SNMP transport adapter — pysnmp asyncio API isolated here.

Root cause of walk regression (fixed here)
--------------------------------------------
pysnmp >= 6.x changed nextCmd from an async-generator to a plain
coroutine that returns ONE row per call:

    (errInd, errSt, errIdx, varBindTable) = await nextCmd(...)

The previous code used ``async for ... in nextCmd(...)`` which is only
valid for async-generator functions.  That caused a TypeError at runtime
which was silently swallowed in collector.py's try/except, so every walk
returned an empty dict and every non-system collector reported
supported=False.

Fix: walk() now calls ``await nextCmd(...)`` in a while-loop, advancing
the current OID with each iteration until the subtree is exhausted or an
error occurs.  getCmd() was already correct (single await).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextvars
import logging
import hashlib
import hmac
import json
import os
import queue
import threading
import time
from typing import Any

from .credentials import SNMPCredentials
from .security import AUTH_PROTOCOLS, PRIVACY_PROTOCOLS, protocol_name
from backend.config.settings import get_settings

logger = logging.getLogger(__name__)
_FINGERPRINT_KEY = os.urandom(32)

_worker_engine: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "snmp_worker_engine", default=None
)

# Hard cap: never walk more than this many rows per OID tree.
# Prevents runaway walks on large ARP/MAC tables.
_MAX_WALK_ROWS = 2000
_CANCELLATION_MARGIN_SECONDS = 0.05


class _SNMPWorker:
    """One thread owning one reusable asyncio loop and SnmpEngine."""

    def __init__(self, index: int) -> None:
        self.index = index
        self.queue: queue.Queue[Any] = queue.Queue()
        self.thread = threading.Thread(
            target=self._run, name=f"snmp-worker-{index}", daemon=True
        )
        self.thread.start()

    def _run(self) -> None:
        from pysnmp.hlapi.asyncio import SnmpEngine  # noqa: PLC0415

        def create_runtime() -> tuple[Any, Any]:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            new_engine = SnmpEngine()
            logger.debug("SNMP_ENGINE_CREATED worker=%d", self.index)
            return new_loop, new_engine

        def close_runtime(current_loop: Any, current_engine: Any) -> None:
            try:
                current_engine.transportDispatcher.closeDispatcher()
            except Exception:
                logger.exception("Failed to close SNMP worker engine %d", self.index)
            if not current_loop.is_closed():
                for task in asyncio.all_tasks(current_loop):
                    task.cancel()
                current_loop.close()

        loop, engine = create_runtime()
        logger.debug("SNMP_WORKER_STARTED worker=%d", self.index)
        try:
            while True:
                item = self.queue.get()
                if item is None:
                    self.queue.task_done()
                    break
                coro, timeout, future = item
                token = _worker_engine.set(engine)
                try:
                    if not future.set_running_or_notify_cancel():
                        coro.close()
                        continue
                    logger.debug("SNMP_ENGINE_REUSED worker=%d", self.index)
                    worker_timeout = max(
                        timeout * 0.9,
                        timeout - _CANCELLATION_MARGIN_SECONDS,
                    )
                    value = loop.run_until_complete(
                        asyncio.wait_for(coro, timeout=worker_timeout)
                    )
                    future.set_result(value)
                except BaseException as exc:
                    if not future.done():
                        future.set_exception(exc)
                    if isinstance(exc, RuntimeError):
                        close_runtime(loop, engine)
                        loop, engine = create_runtime()
                        logger.debug("SNMP_WORKER_RECOVERED worker=%d", self.index)
                finally:
                    _worker_engine.reset(token)
                    self.queue.task_done()
        finally:
            close_runtime(loop, engine)
            logger.debug("SNMP_WORKER_STOPPED worker=%d", self.index)


class SNMPWorkerPool:
    """Fixed-size dispatcher for worker-owned SNMP runtime state."""

    def __init__(self, workers: int = 8) -> None:
        self.worker_count = workers
        self._lock = threading.Lock()
        self._workers: list[_SNMPWorker] = []
        self._next = 0
        self._accepting = True

    def _ensure_started_locked(self) -> None:
        if not self._workers:
            self._workers = [_SNMPWorker(index) for index in range(self.worker_count)]

    def submit(self, coro: Any, timeout: float) -> Any:
        with self._lock:
            if not self._accepting:
                coro.close()
                raise RuntimeError("SNMP worker pool is shut down")
            self._ensure_started_locked()
            worker = self._workers[self._next % len(self._workers)]
            self._next += 1
            future: concurrent.futures.Future = concurrent.futures.Future()
            worker.queue.put((coro, timeout, future))
        try:
            return future.result(timeout=timeout)
        except (asyncio.TimeoutError, concurrent.futures.TimeoutError) as exc:
            future.cancel()
            raise TimeoutError(f"SNMP operation timed out after {timeout:.1f}s") from exc

    def shutdown(self) -> None:
        with self._lock:
            if not self._accepting:
                return
            self._accepting = False
            workers = list(self._workers)
        for worker in workers:
            worker.queue.join()
            worker.queue.put(None)
        for worker in workers:
            worker.thread.join()


_snmp_workers = SNMPWorkerPool(workers=8)


def _run_in_thread(coro: Any, timeout: float) -> Any:
    """Run a coroutine on a dedicated worker's persistent loop and engine."""
    return _snmp_workers.submit(coro, timeout)


def shutdown_snmp_workers() -> None:
    """Stop accepting work and deterministically release worker resources."""
    _snmp_workers.shutdown()


def _engine_for_operation(factory: Any) -> tuple[Any, bool]:
    engine = _worker_engine.get()
    if engine is not None:
        return engine, False
    return factory(), True


class SNMPClient:
    """
    Synchronous SNMP GET + WALK facade over pysnmp's asyncio API.

    Both methods are safe to call from a synchronous FastAPI route handler.
    """

    def __init__(
        self,
        credentials: SNMPCredentials,
        timeout: float | None = None,
        retries: int | None = None,
        operation_timeout: float | None = None,
        device_id: int | None = None,
    ) -> None:
        settings = get_settings()
        self.credentials = credentials
        self.device_id = device_id
        self.timeout = settings.snmp_request_timeout if timeout is None else timeout
        self.retries = settings.snmp_retries if retries is None else retries
        self.operation_timeout = (
            settings.snmp_operation_timeout
            if operation_timeout is None else operation_timeout
        )
        fingerprint_payload = json.dumps({
            "version": credentials.version.lower(),
            "community": credentials.community,
            "username": credentials.username,
            "auth_protocol": credentials.auth_protocol,
            "auth_password": credentials.auth_password,
            "privacy_protocol": credentials.privacy_protocol,
            "privacy_password": credentials.privacy_password,
            "security_level": credentials.security_level,
            "port": credentials.port,
        }, sort_keys=True, separators=(",", ":")).encode()
        self._credential_fingerprint = hmac.new(
            _FINGERPRINT_KEY, fingerprint_payload, hashlib.sha256
        ).hexdigest()

    def _cached(self, host: str, operation: tuple[Any, ...], request: Any) -> dict[str, Any]:
        # A stable database device identity is mandatory for reuse. Discovery
        # and ad-hoc callers retain the exact pre-cache network behavior.
        if self.device_id is None:
            return request()
        from .raw_cache import get_raw_snmp_cache  # noqa: PLC0415
        settings = get_settings()
        key = (
            self.device_id,
            host,
            self.credentials.port,
            self.credentials.version.lower(),
            operation,
            self._credential_fingerprint,
        )
        return get_raw_snmp_cache(
            settings.snmp_raw_cache_ttl_seconds,
            settings.snmp_raw_cache_max_entries,
        ).execute(key, request)

    # ------------------------------------------------------------------
    # Auth object (rebuilt per-call to avoid sharing state across threads)
    # ------------------------------------------------------------------

    def _make_auth(self) -> Any:
        from pysnmp.hlapi.asyncio import CommunityData, UsmUserData  # noqa: PLC0415
        if not self.credentials.is_v3:
            return CommunityData(
                self.credentials.community or "public", mpModel=1
            )

        import pysnmp.hlapi.asyncio as hlapi  # noqa: PLC0415

        kwargs: dict[str, Any] = {
            "userName": self.credentials.username or "",
        }
        if self.credentials.auth_protocol:
            kwargs["authKey"]      = self.credentials.auth_password
            kwargs["authProtocol"] = getattr(
                hlapi,
                AUTH_PROTOCOLS[protocol_name(self.credentials.auth_protocol)],
            )
        if self.credentials.privacy_protocol:
            kwargs["privKey"]      = self.credentials.privacy_password
            kwargs["privProtocol"] = getattr(
                hlapi,
                PRIVACY_PROTOCOLS[protocol_name(self.credentials.privacy_protocol)],
            )
        return UsmUserData(**kwargs)

    # Kept for compatibility with older internal callers and regression tests.
    def _auth(self) -> Any:
        return self._make_auth()

    # ------------------------------------------------------------------
    # GET — single request for a list of scalar OIDs
    # ------------------------------------------------------------------

    def get(self, host: str, oids: tuple[str, ...]) -> dict[str, Any]:
        """
        Issue a single SNMP GET for *oids* and return {oid_str: value_str}.
        Raises OSError if the agent returns an error indication.
        """
        from pysnmp.hlapi.asyncio import (  # noqa: PLC0415
            ContextData, ObjectIdentity, ObjectType,
            SnmpEngine, UdpTransportTarget, getCmd,
        )

        t0 = time.perf_counter()

        async def _run() -> Any:
            engine, _owned = _engine_for_operation(SnmpEngine)
            target = UdpTransportTarget(
                (host, self.credentials.port or 161), timeout=self.timeout, retries=self.retries
            )
            return await getCmd(
                engine,
                self._make_auth(),
                target,
                ContextData(),
                *(ObjectType(ObjectIdentity(oid)) for oid in oids),
            )

        try:
            def _request() -> dict[str, Any]:
                errInd, errSt, _errIdx, var_binds = _run_in_thread(
                    _run(), self.operation_timeout
                )
                if errInd or errSt:
                    raise OSError(str(errInd or errSt))
                return {str(oid): value.prettyPrint() for oid, value in var_binds}

            result = self._cached(host, ("get", tuple(oids)), _request)
        finally:
            from backend.observability import record_snmp_duration  # noqa: PLC0415
            record_snmp_duration((time.perf_counter() - t0) * 1000)
        elapsed = round((time.perf_counter() - t0) * 1000, 1)

        logger.debug(
            "GET %s oids=%d result=%d ms=%.1f",
            host, len(oids), len(result), elapsed,
        )
        return result

    # ------------------------------------------------------------------
    # WALK — iterative GETNEXT over a subtree
    # ------------------------------------------------------------------

    def walk(
        self,
        host: str,
        root_oid: str,
        operation_timeout: float | None = None,
    ) -> dict[str, Any]:
        """Fetch table rows in bounded GETBULK batches, with GETNEXT fallback.

        Stops at subtree boundaries, end-of-MIB, non-increasing OIDs, the row
        limit, or the operation deadline. Always closes the SNMP dispatcher.
        """
        from pysnmp.hlapi.asyncio import (  # noqa: PLC0415
            ContextData, ObjectIdentity, ObjectType,
            SnmpEngine, UdpTransportTarget, nextCmd, bulkCmd,
        )

        t0       = time.perf_counter()
        root_dot = root_oid.rstrip(".") + "."
        deadline = self.operation_timeout if operation_timeout is None else operation_timeout

        async def _run() -> dict[str, Any]:
            result:  dict[str, Any] = {}
            engine, owns_engine = _engine_for_operation(SnmpEngine)
            auth    = self._make_auth()
            target  = UdpTransportTarget(
                (host, self.credentials.port or 161), timeout=self.timeout, retries=self.retries
            )
            ctx = ContextData()

            # Seed: start from the root OID
            current_var_binds = [ObjectType(ObjectIdentity(root_oid))]
            rows = 0

            use_bulk = True
            previous_oid = tuple(int(part) for part in root_oid.strip(".").split("."))
            try:
                while rows < _MAX_WALK_ROWS:
                    if use_bulk:
                        response = await bulkCmd(
                            engine, auth, target, ctx, 0, min(25, _MAX_WALK_ROWS - rows),
                            *current_var_binds, lexicographicMode=False,
                        )
                    else:
                        response = await nextCmd(
                            engine, auth, target, ctx, *current_var_binds,
                            lexicographicMode=False,
                        )
                    errInd, errSt, _errIdx, var_bind_table = response
                    if errInd:
                        logger.debug("WALK %s %s error=%s after %d rows", host, root_oid, errInd, rows)
                        break
                    if int(errSt):
                        # Some agents reject GETBULK (e.g. tooBig). Retry the
                        # same cursor with GETNEXT without dropping prior rows.
                        if use_bulk:
                            use_bulk = False
                            continue
                        break
                    if not var_bind_table:
                        break
                    for row_vars in var_bind_table:
                        if not row_vars:
                            return result
                        for oid_obj, val_obj in row_vars:
                            oid = str(oid_obj)
                            numeric_oid = tuple(int(part) for part in oid.split("."))
                            from pysnmp.proto.rfc1905 import endOfMibView, noSuchObject, noSuchInstance
                            terminal = any(marker.isSameTypeWith(val_obj) for marker in (endOfMibView, noSuchObject, noSuchInstance))
                            if terminal or not oid.startswith(root_dot) or numeric_oid <= previous_oid:
                                return result
                            result[oid] = val_obj.prettyPrint()
                            previous_oid = numeric_oid
                            rows += 1
                            if rows >= _MAX_WALK_ROWS:
                                return result
                        current_var_binds = row_vars
                return result
            finally:
                if owns_engine:
                    engine.transportDispatcher.closeDispatcher()

        try:
            result = self._cached(
                host,
                ("walk", root_oid.rstrip(".")),
                lambda: _run_in_thread(_run(), deadline),
            )
        finally:
            from backend.observability import record_snmp_duration  # noqa: PLC0415
            record_snmp_duration((time.perf_counter() - t0) * 1000)
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        logger.debug(
            "WALK %s root=%s rows=%d ms=%.1f",
            host, root_oid, len(result), elapsed,
        )
        return result
