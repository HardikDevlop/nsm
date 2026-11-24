"""One-shot Linux metric collection over SNMPv3.

The collector uses dynamic table walks and stores raw counters in the Linux
module's sample JSON so the next explicit collection can calculate deltas.
It never registers with or changes the existing SNMP scheduler.
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass
import re
from typing import Any, Literal

from backend.snmp.client import SNMPClient
from backend.snmp.credentials import SNMPCredentials


# These are standard MIB roots, not device/interface/disk-specific values.
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"
IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"
IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
IF_HC_IN_UCAST_PKTS = "1.3.6.1.2.1.31.1.1.1.7"
IF_HC_OUT_UCAST_PKTS = "1.3.6.1.2.1.31.1.1.1.11"
IF_IN_UCAST_PKTS = "1.3.6.1.2.1.2.2.1.11"
IF_OUT_UCAST_PKTS = "1.3.6.1.2.1.2.2.1.17"
IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"
IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"
IF_IN_DISCARDS = "1.3.6.1.2.1.2.2.1.13"
IF_OUT_DISCARDS = "1.3.6.1.2.1.2.2.1.19"

HR_PROCESSOR_LOAD = "1.3.6.1.2.1.25.3.3.1.2"
HR_STORAGE_DESCR = "1.3.6.1.2.1.25.2.3.1.3"
HR_STORAGE_UNITS = "1.3.6.1.2.1.25.2.3.1.4"
HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"
HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"
MEM_TOTAL_REAL = "1.3.6.1.4.1.2021.4.5.0"
MEM_AVAIL_REAL = "1.3.6.1.4.1.2021.4.6.0"
MEM_TOTAL_SWAP = "1.3.6.1.4.1.2021.4.3.0"
MEM_AVAIL_SWAP = "1.3.6.1.4.1.2021.4.4.0"
# UCD-SNMP laLoad values are under laLoad.5, not laLoad.3 (the latter is
# the string description column and cannot be converted to a number).
LOAD_1 = "1.3.6.1.4.1.2021.10.1.5.1"
LOAD_5 = "1.3.6.1.4.1.2021.10.1.5.2"
LOAD_15 = "1.3.6.1.4.1.2021.10.1.5.3"
DISK_IO_DEVICE = "1.3.6.1.4.1.2021.13.15.1.1.2"
DISK_IO_READ_BYTES = "1.3.6.1.4.1.2021.13.15.1.1.3"
DISK_IO_WRITE_BYTES = "1.3.6.1.4.1.2021.13.15.1.1.4"

# Linux net-snmp exposes CPU percentages through UCD-SNMP-MIB even when the
# HOST-RESOURCES processor table is disabled.
UCD_CPU_USER = "1.3.6.1.4.1.2021.11.9.0"
UCD_CPU_SYSTEM = "1.3.6.1.4.1.2021.11.10.0"
UCD_CPU_IDLE = "1.3.6.1.4.1.2021.11.11.0"

_MEMORY_EXTEND_KEYS = frozenset(("version", "MemTotalKiB", "MemAvailableKiB"))
_MEMORY_EXTEND_INTEGER = re.compile(r"[0-9]+\Z")
LINUX_MEMORY_EXTEND_TOKEN = "agnigateLinuxMem"
_NS_EXTEND_OUTPUT1_LINE_BASE = "1.3.6.1.4.1.8072.1.3.2.3.1.1"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LinuxEffectiveMemoryResult:
    """Validated Linux effective-memory values from a Net-SNMP extension."""

    version: int
    total_kib: int
    available_kib: int
    total_bytes: int
    available_bytes: int
    used_bytes: int
    utilization_percent: float
    source: str = "net-snmp-extend"
    semantic: str = "linux_proc_meminfo_memavailable"


@dataclass(frozen=True)
class LinuxEffectiveMemorySNMPResult:
    """Outcome of the opt-in effective-memory SNMP query."""

    status: Literal["success", "unavailable", "error"]
    data: LinuxEffectiveMemoryResult | None = None
    error_code: str | None = None


def linux_memory_extend_output_oid(token: str = LINUX_MEMORY_EXTEND_TOKEN) -> str:
    """Build nsExtendOutput1Line's numeric OID for an ASCII token index."""
    if not token:
        raise ValueError("Net-SNMP extend token must not be empty")
    index = ".".join((str(len(token)), *(str(ord(char)) for char in token)))
    return f"{_NS_EXTEND_OUTPUT1_LINE_BASE}.{index}"


def parse_linux_effective_memory_extend_output(output: str) -> LinuxEffectiveMemoryResult:
    """Parse the strict version-1 Linux MemAvailable extension response.

    The parser is intentionally isolated from SNMP transport and persistence.
    It rejects unknown or duplicate keys so an incomplete or changed agent
    response cannot be mistaken for a valid effective-memory sample.
    """
    if not isinstance(output, str):
        raise ValueError("memory extension output must be text")

    fields: dict[str, str] = {}
    tokens = output.split()
    if not tokens:
        raise ValueError("memory extension output is empty")
    for token in tokens:
        if token.count("=") != 1:
            raise ValueError(f"malformed memory extension field: {token!r}")
        key, value = token.split("=", 1)
        if key not in _MEMORY_EXTEND_KEYS:
            raise ValueError(f"unknown memory extension field: {key!r}")
        if key in fields:
            raise ValueError(f"duplicate memory extension field: {key!r}")
        if not value or not _MEMORY_EXTEND_INTEGER.fullmatch(value):
            raise ValueError(f"invalid integer for memory extension field: {key!r}")
        fields[key] = value

    if set(fields) != _MEMORY_EXTEND_KEYS:
        missing = sorted(_MEMORY_EXTEND_KEYS - set(fields))
        raise ValueError(f"missing memory extension fields: {', '.join(missing)}")

    version = int(fields["version"])
    total_kib = int(fields["MemTotalKiB"])
    available_kib = int(fields["MemAvailableKiB"])
    if version != 1:
        raise ValueError(f"unsupported memory extension version: {version}")
    if total_kib <= 0:
        raise ValueError("MemTotalKiB must be positive")
    if available_kib > total_kib:
        raise ValueError("MemAvailableKiB must not exceed MemTotalKiB")

    total_bytes = total_kib * 1024
    available_bytes = available_kib * 1024
    used_bytes = total_bytes - available_bytes
    return LinuxEffectiveMemoryResult(
        version=version,
        total_kib=total_kib,
        available_kib=available_kib,
        total_bytes=total_bytes,
        available_bytes=available_bytes,
        used_bytes=used_bytes,
        utilization_percent=(used_bytes / total_bytes) * 100,
    )


def collect_linux_effective_memory_via_extend(
    host: str,
    credentials: SNMPCredentials,
    timeout_seconds: float = 10.0,
) -> LinuxEffectiveMemorySNMPResult:
    """Query and parse the opt-in Net-SNMP effective-memory extension.

    This helper is deliberately separate from ``collect_linux_metrics`` and
    has no persistence, scheduler, alert, or legacy-metric fallback behavior.
    """
    if timeout_seconds <= 0:
        return LinuxEffectiveMemorySNMPResult("error", error_code="invalid_timeout")

    client = SNMPClient(
        credentials,
        timeout=min(timeout_seconds, 5.0),
        retries=0,
        operation_timeout=timeout_seconds,
    )
    oid = linux_memory_extend_output_oid()
    try:
        values = client.get(host, (oid,))
    except TimeoutError:
        return LinuxEffectiveMemorySNMPResult("unavailable", error_code="timeout")
    except OSError as exc:
        message = str(exc).lower()
        if any(marker in message for marker in ("no such", "nosuch", "unknown object", "not found")):
            code = "no_such_instance"
        elif any(marker in message for marker in ("authorization", "access", "not authorized", "permission")):
            code = "access_denied"
        else:
            code = "snmp_error"
        return LinuxEffectiveMemorySNMPResult("unavailable", error_code=code)
    except Exception:
        return LinuxEffectiveMemorySNMPResult("error", error_code="snmp_error")

    raw = values.get(oid)
    if raw is None:
        return LinuxEffectiveMemorySNMPResult("unavailable", error_code="no_such_instance")
    if isinstance(raw, str) and any(marker in raw.lower() for marker in ("no such", "nosuch", "unknown object")):
        return LinuxEffectiveMemorySNMPResult("unavailable", error_code="no_such_instance")
    if not isinstance(raw, str):
        return LinuxEffectiveMemorySNMPResult("error", error_code="unsupported_response")
    try:
        parsed = parse_linux_effective_memory_extend_output(raw)
    except ValueError:
        return LinuxEffectiveMemorySNMPResult("error", error_code="malformed_output")
    return LinuxEffectiveMemorySNMPResult("success", data=parsed)


class LinuxMetricCollectionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _walk_by_index(client: SNMPClient, root: str, warnings: list[str]) -> dict[str, Any]:
    try:
        return {oid.rsplit(".", 1)[-1]: value for oid, value in client.walk("", root).items()}
    except Exception as exc:
        warnings.append(f"unsupported_or_unavailable:{root}")
        return {}


def _walk_host(client: SNMPClient, host: str, root: str, warnings: list[str]) -> dict[str, Any]:
    try:
        return {oid.rsplit(".", 1)[-1]: value for oid, value in client.walk(host, root).items()}
    except Exception:
        warnings.append(f"unsupported_or_unavailable:{root}")
        return {}


def _get(client: SNMPClient, host: str, oid: str, warnings: list[str]) -> Any:
    try:
        return client.get(host, (oid,)).get(oid)
    except Exception:
        warnings.append(f"unsupported_or_unavailable:{oid}")
        return None


def _counter_delta(current: float | None, previous: float | None, bits: int) -> float | None:
    if current is None or previous is None:
        return None
    if current >= previous:
        return current - previous
    modulus = float(1 << bits)
    wrapped = current + modulus - previous
    # A decrease larger than one full counter range is a reset, not a wrap.
    return wrapped if wrapped < modulus / 2 else None


def _rate(current: float | None, previous: float | None, elapsed: float, bits: int) -> float | None:
    delta = _counter_delta(current, previous, bits)
    return round(delta / elapsed, 3) if delta is not None and elapsed > 0 else None


def _counter_map(raw: dict[str, Any]) -> dict[str, float]:
    return {index: number for index, value in raw.items() if (number := _number(value)) is not None}


def _sum_optional(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _is_authentication_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token in message for token in ("authorization", "authentication", "unknown user", "unknowncommunity", "usm"))


def collect_linux_metrics(host: str, request: Any, previous: Any | None = None) -> dict[str, Any]:
    credentials = SNMPCredentials(
        version="v3",
        username=request.username,
        auth_protocol=request.auth_protocol,
        auth_password=request.auth_password.get_secret_value() if request.auth_password else None,
        privacy_protocol=request.privacy_protocol,
        privacy_password=request.privacy_password.get_secret_value() if request.privacy_password else None,
        security_level=request.security_level,
    )
    started = time.monotonic()
    warnings: list[str] = []

    def ensure_time() -> None:
        if time.monotonic() - started > request.timeout_seconds:
            raise LinuxMetricCollectionError("timeout", "SNMP metric collection timed out")

    def walk(root: str, report_warning: bool = True) -> dict[str, Any]:
        ensure_time()
        try:
            remaining = max(0.1, request.timeout_seconds - (time.monotonic() - started))
            client = SNMPClient(credentials, timeout=min(remaining, 5.0), retries=0, operation_timeout=remaining)
            return {oid.rsplit(".", 1)[-1]: value for oid, value in client.walk(host, root).items()}
        except TimeoutError as exc:
            raise LinuxMetricCollectionError("timeout", "SNMP metric collection timed out") from exc
        except Exception as exc:
            if _is_authentication_error(exc):
                raise LinuxMetricCollectionError("authentication_failed", "SNMPv3 authentication failed") from exc
            if report_warning:
                warnings.append(f"unsupported_or_unavailable:{root}")
            return {}

    def get(oid: str, report_warning: bool = True) -> Any:
        ensure_time()
        try:
            remaining = max(0.1, request.timeout_seconds - (time.monotonic() - started))
            client = SNMPClient(credentials, timeout=min(remaining, 5.0), retries=0, operation_timeout=remaining)
            return client.get(host, (oid,)).get(oid)
        except TimeoutError as exc:
            raise LinuxMetricCollectionError("timeout", "SNMP metric collection timed out") from exc
        except Exception as exc:
            if _is_authentication_error(exc):
                raise LinuxMetricCollectionError("authentication_failed", "SNMPv3 authentication failed") from exc
            if report_warning:
                warnings.append(f"unsupported_or_unavailable:{oid}")
            return None

    names = walk(IF_NAME, report_warning=False) or walk(IF_DESCR, report_warning=False)
    oper_status = walk(IF_OPER_STATUS, report_warning=False)
    hc_in = walk(IF_HC_IN_OCTETS, report_warning=False)
    hc_out = walk(IF_HC_OUT_OCTETS, report_warning=False)
    in_octets = hc_in or walk(IF_IN_OCTETS, report_warning=False)
    out_octets = hc_out or walk(IF_OUT_OCTETS, report_warning=False)
    hc_in_pkts = walk(IF_HC_IN_UCAST_PKTS, report_warning=False)
    hc_out_pkts = walk(IF_HC_OUT_UCAST_PKTS, report_warning=False)
    in_pkts = hc_in_pkts or walk(IF_IN_UCAST_PKTS, report_warning=False)
    out_pkts = hc_out_pkts or walk(IF_OUT_UCAST_PKTS, report_warning=False)
    in_errors = walk(IF_IN_ERRORS, report_warning=False)
    out_errors = walk(IF_OUT_ERRORS, report_warning=False)
    in_discards = walk(IF_IN_DISCARDS, report_warning=False)
    out_discards = walk(IF_OUT_DISCARDS, report_warning=False)

    if not names:
        warnings.append("Interface data unavailable: SNMP agent did not expose IF-MIB tables")

    current_interfaces: dict[str, dict[str, Any]] = {}
    interface_indexes = set(names) | set(in_octets) | set(out_octets)
    counter_bits = 64 if hc_in or hc_out or hc_in_pkts or hc_out_pkts else 32
    previous_counters = ((previous.details or {}).get("counters", {}) if previous else {})
    previous_timestamp = _number(previous_counters.get("timestamp"))
    elapsed = time.time() - previous_timestamp if previous_timestamp else None
    previous_interfaces = previous_counters.get("interfaces", {})
    rx_rate = tx_rate = packet_rate = error_rate = drop_rate = 0.0
    has_rx = has_tx = has_packets = has_errors = has_drops = False
    for index in sorted(interface_indexes, key=lambda value: int(value) if value.isdigit() else value):
        in_error = _number(in_errors.get(index))
        out_error = _number(out_errors.get(index))
        in_drop = _number(in_discards.get(index))
        out_drop = _number(out_discards.get(index))
        current = {
            "name": str(names.get(index) or f"ifIndex-{index}"),
            "rx_bytes": _number(in_octets.get(index)),
            "tx_bytes": _number(out_octets.get(index)),
            "rx_packets": _number(in_pkts.get(index)),
            "tx_packets": _number(out_pkts.get(index)),
            "errors": _sum_optional([in_error, out_error]),
            "drops": _sum_optional([in_drop, out_drop]),
            "oper_status": _number(oper_status.get(index)),
            "counter_bits": counter_bits,
        }
        previous = previous_interfaces.get(index, {})
        for field in ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets", "errors", "drops"):
            current[field] = current[field]
        if elapsed and elapsed > 0:
            for field, accumulator in (("rx_bytes", "rx_rate"), ("tx_bytes", "tx_rate"), ("rx_packets", "packet_rate"), ("tx_packets", "packet_rate"), ("errors", "error_rate"), ("drops", "drop_rate")):
                rate = _rate(current[field], previous.get(field), elapsed, counter_bits)
                if rate is not None:
                    if accumulator == "rx_rate": rx_rate += rate; has_rx = True
                    elif accumulator == "tx_rate": tx_rate += rate; has_tx = True
                    elif accumulator == "packet_rate": packet_rate += rate; has_packets = True
                    elif accumulator == "error_rate": error_rate += rate; has_errors = True
                    elif accumulator == "drop_rate": drop_rate += rate; has_drops = True
        current_interfaces[index] = current

    uptime = _number(get(SYS_UPTIME, report_warning=False))
    processor = [_number(value) for value in walk(HR_PROCESSOR_LOAD, report_warning=False).values()]
    processor = [value for value in processor if value is not None]
    if not processor:
        idle = _number(get(UCD_CPU_IDLE, report_warning=False))
        user = _number(get(UCD_CPU_USER, report_warning=False))
        system = _number(get(UCD_CPU_SYSTEM, report_warning=False))
        if idle is not None:
            processor = [max(0.0, min(100.0, 100.0 - idle))]
        elif user is not None and system is not None:
            processor = [max(0.0, min(100.0, user + system))]
    total_memory = _number(get(MEM_TOTAL_REAL))
    available_memory = _number(get(MEM_AVAIL_REAL))
    total_swap = _number(get(MEM_TOTAL_SWAP))
    available_swap = _number(get(MEM_AVAIL_SWAP))
    storage_descr = walk(HR_STORAGE_DESCR, report_warning=False)
    storage_units = walk(HR_STORAGE_UNITS, report_warning=False)
    storage_size = walk(HR_STORAGE_SIZE, report_warning=False)
    storage_used = walk(HR_STORAGE_USED, report_warning=False)
    disk_values: list[float] = []
    disk_details: list[dict[str, Any]] = []
    for index in set(storage_descr) | set(storage_size):
        size = _number(storage_size.get(index))
        used = _number(storage_used.get(index))
        units = _number(storage_units.get(index)) or 1
        if size and size > 0 and used is not None:
            disk_values.append((used / size) * 100)
            disk_details.append({"index": index, "description": str(storage_descr.get(index) or f"storage-{index}"), "total_bytes": size * units, "used_bytes": used * units, "available_bytes": max(0.0, (size - used) * units), "usage_percent": round((used / size) * 100, 3)})

    disk_io_devices = walk(DISK_IO_DEVICE, report_warning=False)
    disk_io_read = _counter_map(walk(DISK_IO_READ_BYTES, report_warning=False))
    disk_io_write = _counter_map(walk(DISK_IO_WRITE_BYTES, report_warning=False))
    if not disk_values:
        warnings.append("Disk usage unavailable: SNMP agent does not expose HOST-RESOURCES storage data")
    previous_disks = previous_counters.get("disks", {})
    read_rate = write_rate = 0.0
    has_read = has_write = False
    for index in set(disk_io_devices) | set(disk_io_read) | set(disk_io_write):
        previous_disk = previous_disks.get(index, {})
        read = _rate(disk_io_read.get(index), previous_disk.get("read_bytes"), elapsed or 0, 64)
        write = _rate(disk_io_write.get(index), previous_disk.get("write_bytes"), elapsed or 0, 64)
        if read is not None: read_rate += read; has_read = True
        if write is not None: write_rate += write; has_write = True

    memory_used = ((total_memory - available_memory) if total_memory and available_memory is not None else None)
    swap_used = ((total_swap - available_swap) if total_swap and available_swap is not None else None)

    # Keep the legacy UCD-SNMP percentage above unchanged for existing Linux
    # dashboards and threshold evaluation.  The canonical effective-memory
    # sample is stored separately and is consumed only by the normalized
    # aggregation path.
    canonical_timeout = request.timeout_seconds - (time.monotonic() - started)
    canonical = collect_linux_effective_memory_via_extend(
        host,
        credentials,
        timeout_seconds=canonical_timeout,
    )
    canonical_data: dict[str, Any] = {
        "semantic": "linux_proc_meminfo_memavailable",
        "status": canonical.status,
        "source": "net-snmp-extend",
        "usage_percent": None,
        "total_bytes": None,
        "available_bytes": None,
        "used_bytes": None,
    }
    if canonical.status == "success" and canonical.data is not None:
        canonical_data.update({
            "status": "ok",
            "source": canonical.data.source,
            "usage_percent": canonical.data.utilization_percent,
            "total_bytes": canonical.data.total_bytes,
            "available_bytes": canonical.data.available_bytes,
            "used_bytes": canonical.data.used_bytes,
        })
    else:
        canonical_data["error_code"] = canonical.error_code
        logger.warning(
            "LINUX_MEMORY_CANONICAL_UNAVAILABLE host=%s status=%s error_code=%s",
            host,
            canonical.status,
            canonical.error_code,
        )

    details = {
        "cpu_cores": [round(value, 3) for value in processor],
        "memory": {
            "total_bytes": total_memory * 1024 if total_memory is not None else None,
            "used_bytes": memory_used * 1024 if memory_used is not None else None,
            "available_bytes": available_memory * 1024 if available_memory is not None else None,
            "legacy_source": "ucd-snmp",
            "canonical": canonical_data,
        },
        "swap": {"total_bytes": total_swap * 1024 if total_swap is not None else None, "used_bytes": swap_used * 1024 if swap_used is not None else None, "available_bytes": available_swap * 1024 if available_swap is not None else None},
        "disk_devices": disk_details,
        "counters": {"timestamp": time.time(), "interfaces": current_interfaces, "disks": {index: {"read_bytes": disk_io_read.get(index), "write_bytes": disk_io_write.get(index)} for index in set(disk_io_devices) | set(disk_io_read) | set(disk_io_write)}},
        "warnings": warnings,
        "counter_bits": counter_bits,
    }

    # `memory_percent` is the public metric consumed by the dashboard and
    # threshold evaluator. Prefer the canonical /proc/meminfo calculation
    # (MemTotal - MemAvailable), and only fall back to the legacy SNMP value
    # when the canonical extension is unavailable.
    canonical_memory_percent = _number(canonical_data.get("usage_percent"))
    effective_memory_percent = (
        canonical_memory_percent
        if canonical_memory_percent is not None
        else (round(min(100.0, (memory_used / total_memory) * 100), 3) if total_memory and memory_used is not None else None)
    )

    return {
        "collection_status": "success",
        "cpu_percent": round(sum(processor) / len(processor), 3) if processor else None,
        "memory_percent": effective_memory_percent,
        "swap_percent": round(((total_swap - available_swap) / total_swap) * 100, 3) if total_swap and available_swap is not None else None,
        "disk_percent": round(sum(disk_values) / len(disk_values), 3) if disk_values else None,
        "disk_io_read_bytes_per_sec": round(read_rate, 3) if has_read else None,
        "disk_io_write_bytes_per_sec": round(write_rate, 3) if has_write else None,
        "load_1m": _number(get(LOAD_1)),
        "load_5m": _number(get(LOAD_5)),
        "load_15m": _number(get(LOAD_15)),
        "uptime_seconds": round(uptime / 100, 3) if uptime is not None else None,
        "network_rx_bytes_per_sec": round(rx_rate, 3) if has_rx else None,
        "network_tx_bytes_per_sec": round(tx_rate, 3) if has_tx else None,
        "packets_per_sec": round(packet_rate, 3) if has_packets else None,
        "interface_errors": round(error_rate, 3) if has_errors else None,
        "interface_drops": round(drop_rate, 3) if has_drops else None,
        "network_rx_bytes": _sum_optional([item["rx_bytes"] for item in current_interfaces.values()]),
        "network_tx_bytes": _sum_optional([item["tx_bytes"] for item in current_interfaces.values()]),
        "details": details,
        "error_message": None,
    }
