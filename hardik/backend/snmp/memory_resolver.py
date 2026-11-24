"""Canonical Linux memory resolution for the generic SNMP collector."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.linux_monitoring.metrics import (
    LinuxEffectiveMemoryResult,
    parse_linux_effective_memory_extend_output,
    linux_memory_extend_output_oid,
)
from .client import SNMPClient
from .credentials import SNMPCredentials


_LINUX_IDENTITY = re.compile(
    r"linux|ubuntu|debian|centos|rhel|fedora|suse|alpine|net-snmp",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CanonicalMemoryResolution:
    """Non-fatal result of an optional canonical Linux memory query."""

    eligible: bool
    status: str
    data: LinuxEffectiveMemoryResult | None = None
    error_code: str | None = None


def linux_memory_extension_eligible(
    *,
    device_type: str | None,
    sys_descr: Any,
) -> bool:
    """Return true only when sysDescr explicitly identifies Linux/net-snmp.

    Linux systems may be classified as servers, hypervisors, NAS devices,
    routers, switches, or unknown devices by the general identity detector.
    Explicit identity text is the safety boundary for Linux semantics.
    """
    del device_type
    return bool(_LINUX_IDENTITY.search(str(sys_descr or "")))


def resolve_canonical_linux_memory(
    host: str,
    credentials: SNMPCredentials,
    *,
    device_type: str | None,
    sys_descr: Any,
    timeout_seconds: float | None = None,
) -> CanonicalMemoryResolution:
    """Query the existing extension without making memory collection fatal."""
    if not linux_memory_extension_eligible(device_type=device_type, sys_descr=sys_descr):
        return CanonicalMemoryResolution(eligible=False, status="ineligible")

    timeout = float(timeout_seconds or getattr(credentials, "timeout", 3.0) or 3.0)
    if timeout <= 0:
        return CanonicalMemoryResolution(
            eligible=True, status="unavailable", error_code="invalid_timeout"
        )

    oid = linux_memory_extend_output_oid()
    try:
        client = SNMPClient(
            credentials,
            timeout=min(timeout, 5.0),
            retries=0,
            operation_timeout=timeout,
        )
        values = client.get(host, (oid,))
        raw = values.get(oid)
    except TimeoutError:
        return CanonicalMemoryResolution(True, "unavailable", error_code="timeout")
    except OSError as exc:
        message = str(exc).lower()
        if any(marker in message for marker in ("no such", "nosuch", "unknown object", "not found")):
            code = "no_such_instance"
        elif any(marker in message for marker in ("authorization", "access", "not authorized", "permission")):
            code = "access_denied"
        else:
            code = "snmp_error"
        return CanonicalMemoryResolution(True, "unavailable", error_code=code)
    except Exception:
        return CanonicalMemoryResolution(True, "unavailable", error_code="snmp_error")

    if raw is None:
        return CanonicalMemoryResolution(True, "unavailable", error_code="no_such_instance")
    if isinstance(raw, str) and any(marker in raw.lower() for marker in ("no such", "nosuch", "unknown object")):
        return CanonicalMemoryResolution(True, "unavailable", error_code="no_such_instance")
    if not isinstance(raw, str):
        return CanonicalMemoryResolution(True, "invalid", error_code="unsupported_response")

    try:
        parsed = parse_linux_effective_memory_extend_output(raw)
    except ValueError:
        return CanonicalMemoryResolution(True, "invalid", error_code="malformed_output")
    return CanonicalMemoryResolution(True, "canonical", data=parsed)
