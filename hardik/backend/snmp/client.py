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
import logging
import time
from typing import Any

from .credentials import SNMPCredentials
from .security import AUTH_PROTOCOLS, PRIVACY_PROTOCOLS, protocol_name
from backend.config.settings import get_settings

logger = logging.getLogger(__name__)

# One shared executor — walks are I/O-bound, 8 workers handles concurrent
# per-device polling without starving the main thread pool.
_snmp_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=8,
    thread_name_prefix="snmp-walk",
)

# Hard cap: never walk more than this many rows per OID tree.
# Prevents runaway walks on large ARP/MAC tables.
_MAX_WALK_ROWS = 2000
_CANCELLATION_MARGIN_SECONDS = 0.05


def _run_in_thread(coro: Any, timeout: float) -> Any:
    """
    Run *coro* in a dedicated thread that owns its own event loop.

    This is necessary because FastAPI/uvicorn already runs an asyncio loop
    on the main thread; creating a second loop in the same thread raises
    "This event loop is already running".  Running in a ThreadPoolExecutor
    thread gives us a clean loop.

    Cleanup note
    ------------
    pysnmp's AsyncioDispatcher creates internal timer tasks that never
    naturally complete (they wait for a future that is never resolved after
    the SNMP engine is done).  Calling loop.run_until_complete(gather(*pending))
    on them causes an infinite hang.  The correct approach is to cancel them
    WITHOUT awaiting the cancellation, then close the loop immediately.
    """
    def _worker() -> Any:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Enforce the deadline inside the worker as well as on the
            # executor future so asyncio can cancel the in-flight SNMP task.
            worker_timeout = max(
                timeout * 0.9,
                timeout - _CANCELLATION_MARGIN_SECONDS,
            )
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=worker_timeout))
        finally:
            # Cancel pysnmp's pending timer tasks without awaiting them.
            # Awaiting would hang because those tasks wait on unresolvable futures.
            for task in asyncio.all_tasks(loop):
                task.cancel()
            loop.close()

    future = _snmp_executor.submit(_worker)
    try:
        return future.result(timeout=timeout)
    except (asyncio.TimeoutError, concurrent.futures.TimeoutError) as exc:
        future.cancel()
        raise TimeoutError(f"SNMP operation timed out after {timeout:.1f}s") from exc


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
    ) -> None:
        settings = get_settings()
        self.credentials = credentials
        self.timeout = settings.snmp_request_timeout if timeout is None else timeout
        self.retries = settings.snmp_retries if retries is None else retries
        self.operation_timeout = (
            settings.snmp_operation_timeout
            if operation_timeout is None else operation_timeout
        )

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
            target = UdpTransportTarget(
                (host, self.credentials.port or 161), timeout=self.timeout, retries=self.retries
            )
            return await getCmd(
                SnmpEngine(),
                self._make_auth(),
                target,
                ContextData(),
                *(ObjectType(ObjectIdentity(oid)) for oid in oids),
            )

        try:
            errInd, errSt, _errIdx, var_binds = _run_in_thread(
                _run(), self.operation_timeout
            )
        finally:
            from backend.observability import record_snmp_duration  # noqa: PLC0415
            record_snmp_duration((time.perf_counter() - t0) * 1000)
        elapsed = round((time.perf_counter() - t0) * 1000, 1)

        if errInd or errSt:
            raise OSError(str(errInd or errSt))

        result = {str(oid): value.prettyPrint() for oid, value in var_binds}
        logger.debug(
            "GET %s oids=%d result=%d ms=%.1f",
            host, len(oids), len(result), elapsed,
        )
        return result

    # ------------------------------------------------------------------
    # WALK — iterative GETNEXT over a subtree
    # ------------------------------------------------------------------

    def walk(self, host: str, root_oid: str) -> dict[str, Any]:
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

        async def _run() -> dict[str, Any]:
            result:  dict[str, Any] = {}
            engine  = SnmpEngine()
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
                engine.transportDispatcher.closeDispatcher()

        try:
            result = _run_in_thread(_run(), self.operation_timeout)
        finally:
            from backend.observability import record_snmp_duration  # noqa: PLC0415
            record_snmp_duration((time.perf_counter() - t0) * 1000)
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        logger.debug(
            "WALK %s root=%s rows=%d ms=%.1f",
            host, root_oid, len(result), elapsed,
        )
        return result
