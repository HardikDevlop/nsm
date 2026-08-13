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


def _run_in_thread(coro: Any) -> Any:
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
            return loop.run_until_complete(coro)
        finally:
            # Cancel pysnmp's pending timer tasks without awaiting them.
            # Awaiting would hang because those tasks wait on unresolvable futures.
            for task in asyncio.all_tasks(loop):
                task.cancel()
            loop.close()

    future = _snmp_executor.submit(_worker)
    return future.result(timeout=120)


class SNMPClient:
    """
    Synchronous SNMP GET + WALK facade over pysnmp's asyncio API.

    Both methods are safe to call from a synchronous FastAPI route handler.
    """

    def __init__(
        self,
        credentials: SNMPCredentials,
        timeout: float = 5.0,
        retries: int = 1,
    ) -> None:
        self.credentials = credentials
        self.timeout     = timeout
        self.retries     = retries

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
                (host, 161), timeout=self.timeout, retries=self.retries
            )
            return await getCmd(
                SnmpEngine(),
                self._make_auth(),
                target,
                ContextData(),
                *(ObjectType(ObjectIdentity(oid)) for oid in oids),
            )

        errInd, errSt, _errIdx, var_binds = _run_in_thread(_run())
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
        """
        Walk the OID subtree rooted at *root_oid*.

        Returns {oid_str: value_str} for every OID inside the subtree.

        Fix applied here
        ----------------
        pysnmp >= 6.x nextCmd is a *coroutine* (not an async-generator).
        Each ``await nextCmd(...)`` returns exactly ONE (errInd, errSt,
        errIdx, varBindTable) tuple.  To walk a full table we must call it
        repeatedly, passing the last received OID as the next seed, until:
          • the returned OID falls outside the requested subtree, OR
          • the agent returns an error / end-of-MIB.

        The old ``async for ... in nextCmd(...)`` raised:
          TypeError: 'async for' requires __aiter__, got coroutine
        which was swallowed silently, leaving raw={} and making every
        table-based collector return supported=False.
        """
        from pysnmp.hlapi.asyncio import (  # noqa: PLC0415
            ContextData, ObjectIdentity, ObjectType,
            SnmpEngine, UdpTransportTarget, nextCmd,
        )

        t0       = time.perf_counter()
        root_dot = root_oid.rstrip(".") + "."

        async def _run() -> dict[str, Any]:
            result:  dict[str, Any] = {}
            engine  = SnmpEngine()
            auth    = self._make_auth()
            target  = UdpTransportTarget(
                (host, 161), timeout=self.timeout, retries=self.retries
            )
            ctx = ContextData()

            # Seed: start from the root OID
            current_var_binds = [ObjectType(ObjectIdentity(root_oid))]
            rows = 0

            while rows < _MAX_WALK_ROWS:
                # ── single GETNEXT call ──────────────────────────────
                errInd, errSt, _errIdx, var_bind_table = await nextCmd(
                    engine, auth, target, ctx,
                    *current_var_binds,
                    lexicographicMode=False,
                )

                # Agent-level error or end-of-MIB
                if errInd:
                    logger.debug(
                        "WALK %s %s errInd=%s after %d rows",
                        host, root_oid, errInd, rows,
                    )
                    break
                if int(errSt):
                    logger.debug(
                        "WALK %s %s errSt=%s after %d rows",
                        host, root_oid, errSt, rows,
                    )
                    break

                # No data returned → subtree exhausted
                if not var_bind_table:
                    break

                # var_bind_table is a list-of-lists: [[ObjectType, ...], ...]
                # For nextCmd with one seed OID there is always one inner list.
                row_vars = var_bind_table[0]  # list of (OID, value) pairs

                # Check if we have walked past the requested subtree
                first_oid_str = str(row_vars[0][0])
                if not first_oid_str.startswith(root_dot):
                    break

                # Collect this row
                for oid_obj, val_obj in row_vars:
                    result[str(oid_obj)] = val_obj.prettyPrint()

                # Advance seed to the last OID received
                current_var_binds = row_vars
                rows += 1

            return result

        result  = _run_in_thread(_run())
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        logger.debug(
            "WALK %s root=%s rows=%d ms=%.1f",
            host, root_oid, len(result), elapsed,
        )
        return result
