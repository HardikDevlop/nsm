"""Real-time device monitoring engine.

Maintains a registry of devices being monitored, pings each one every 15 seconds
in a background thread, and signals SSE subscribers when status changes occur.

Web Auto-Ping Configuration:
  - PING_INTERVAL = 15 seconds (configurable below)
  - Frontend auto-refreshes monitoring data every 15 seconds to stay in sync
  - Devices are pinged automatically in the background without user action

Performance design:
  - A single background thread handles ALL monitored devices per cycle.
  - Within each cycle, pings run concurrently via ThreadPoolExecutor.
  - threading.Event wakes up SSE coroutines when new data is available.
  - Status history is capped at 20 entries per device to bound memory.

DB persistence:
  - Every ping result is persisted as a DeviceMetric row (latency, packet_loss).
  - Status transitions (up↔down) create DeviceStatusHistory rows and update
    the device's cumulative uptime_seconds / downtime_seconds counters.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import socket
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from backend.utils.time import utc_now

# Indian Standard Time (UTC+5:30)
_IST = timezone(timedelta(hours=5, minutes=30))


def _icmp_db_now() -> datetime:
    """Canonical UTC instant stored as naive UTC for legacy DateTime columns."""
    return utc_now().replace(tzinfo=None)


def _should_advance_last_seen(current: datetime | None, candidate: datetime) -> bool:
    return current is None or candidate >= current
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model for a monitored device
# ---------------------------------------------------------------------------

@dataclass
class MonitoredDevice:
    """Represents a single device under active monitoring."""

    ip: str
    hostname: str = ""
    vendor: str = ""
    mac_address: str | None = None
    site_id: int | None = None
    device_id: int | None = None

    # Live status
    status: str = "unknown"        # up | down | unknown
    last_rtt_ms: float | None = None
    last_check: str | None = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0

    # History (capped at MAX_HISTORY)
    history: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    monitoring_since: float = 0.0
    total_pings: int = 0
    total_up: int = 0
    total_down: int = 0

    # DB-persisted cumulative counters (refreshed on each status transition)
    uptime_seconds: int = 0
    downtime_seconds: int = 0
    last_status_change: str | None = None

    def to_dict(self) -> dict[str, Any]:
        # Compute live uptime/downtime including current session
        live_uptime = self.uptime_seconds
        live_downtime = self.downtime_seconds
        if self.last_status_change:
            try:
                lsc = datetime.fromisoformat(self.last_status_change)
                elapsed = int((_icmp_db_now() - lsc).total_seconds())
                if self.status == "up":
                    live_uptime += elapsed
                elif self.status == "down":
                    live_downtime += elapsed
            except (ValueError, TypeError):
                pass

        return {
            "ip": self.ip,
            "hostname": self.hostname,
            "vendor": self.vendor,
            "mac_address": self.mac_address,
            "site_id": self.site_id,
            "device_id": self.device_id,
            "status": self.status,
            "last_rtt_ms": self.last_rtt_ms,
            "last_check": self.last_check,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "history": self.history[-20:],
            "monitoring_since": self.monitoring_since,
            "total_pings": self.total_pings,
            "total_up": self.total_up,
            "total_down": self.total_down,
            "uptime_pct": round((self.total_up / self.total_pings * 100), 1) if self.total_pings > 0 else 0,
            "uptime_seconds": live_uptime,
            "downtime_seconds": live_downtime,
            "last_status_change": self.last_status_change,
        }


MAX_HISTORY = 20
PING_INTERVAL = 15  # seconds between monitoring cycles (Web Auto-Ping every 15 seconds)
PING_TIMEOUT_MS = 1000
PING_MAX_WORKERS = 20
METRIC_BATCH_SIZE = 100
METRIC_BATCH_INTERVAL = 2.0
DEVICE_CACHE_TTL = 2.0
DEVICE_CACHE_MAX_SIZE = 1024
STATUS_CONFIRMATION_FAILURES = 2
STATUS_CONFIRMATION_SUCCESSES = 2


# ---------------------------------------------------------------------------
# Ping helper (lightweight, no external imports needed)
# ---------------------------------------------------------------------------

_native_icmp_unavailable = False


class _NativeICMPUnavailable(Exception):
    pass


def _icmp_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\0"
    total = sum((data[i] << 8) + data[i + 1] for i in range(0, len(data), 2))
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _native_ping(ip: str, timeout_ms: int) -> tuple[bool, float | None]:
    """One-packet raw ICMP probe. Permission/platform failures are explicit."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except (OSError, PermissionError) as exc:
        raise _NativeICMPUnavailable from exc
    try:
        ident = threading.get_ident() & 0xFFFF
        payload = struct.pack("!d", time.monotonic())
        header = struct.pack("!BBHHH", 8, 0, 0, ident, 1)
        checksum = _icmp_checksum(header + payload)
        packet = struct.pack("!BBHHH", 8, 0, checksum, ident, 1) + payload
        started = time.monotonic()
        sock.settimeout(timeout_ms / 1000.0)
        sock.sendto(packet, (ip, 0))
        while True:
            data, _ = sock.recvfrom(65535)
            if len(data) < 28:
                continue
            ttl = data[8]
            icmp_type, _, _, reply_ident, _ = struct.unpack("!BBHHH", data[20:28])
            if icmp_type == 0 and reply_ident == ident and ttl > 0:
                return True, (time.monotonic() - started) * 1000.0
    except socket.timeout:
        return False, None
    except OSError:
        return False, None
    finally:
        sock.close()


def _subprocess_ping(ip: str, timeout_ms: int) -> tuple[bool, float | None]:
    """Legacy subprocess probe retained as the permission/platform fallback."""
    timeout_s = timeout_ms / 1000.0
    if platform.system().lower() == "windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout_s))), ip]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 2)
        reachable = result.returncode == 0 and "ttl=" in result.stdout.lower()

        # Try to extract RTT from output
        rtt = None
        stdout = result.stdout
        if "time=" in stdout:
            # Linux: time=0.123 ms  or  time<1 ms
            import re
            m = re.search(r"time[=<]([0-9.]+)", stdout)
            if m:
                rtt = float(m.group(1))
        elif "Average =" in stdout:
            # Windows: Average = 1ms
            import re
            m = re.search(r"Average\s*=\s*(\d+)", stdout)
            if m:
                rtt = float(m.group(1))

        return reachable, rtt
    except (subprocess.TimeoutExpired, OSError):
        return False, None


def _ping(ip: str, timeout_ms: int = PING_TIMEOUT_MS) -> tuple[bool, float | None]:
    """Probe using native ICMP when available, otherwise legacy subprocess."""
    global _native_icmp_unavailable
    if not _native_icmp_unavailable:
        try:
            reachable, rtt = _native_ping(ip, timeout_ms)
            logger.debug("ICMP_ENGINE_NATIVE ip=%s", ip)
            return reachable, rtt
        except _NativeICMPUnavailable:
            _native_icmp_unavailable = True
            logger.warning("ICMP_ENGINE_UNAVAILABLE; using subprocess fallback")
    logger.debug("ICMP_ENGINE_FALLBACK ip=%s", ip)
    return _subprocess_ping(ip, timeout_ms)


# ---------------------------------------------------------------------------
# Monitor engine (singleton)
# ---------------------------------------------------------------------------

class MonitorEngine:
    """Singleton engine that pings monitored devices every PING_INTERVAL seconds."""

    def __init__(self) -> None:
        self._devices: dict[str, MonitoredDevice] = {}
        self._lock = threading.Lock()
        self._event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._executor_lock = threading.Lock()
        self._metric_batch: list[tuple[int, float | None, float, datetime, str]] = []
        self._metric_batch_lock = threading.Lock()
        self._metric_batch_event = threading.Event()
        self._metric_batch_stop = threading.Event()
        self._metric_batch_thread = threading.Thread(
            target=self._metric_batch_loop, daemon=True, name="icmp-metric-batch"
        )
        self._metric_batch_thread.start()
        self._device_cache: dict[int, tuple[float, dict[str, Any]]] = {}
        self._device_cache_lock = threading.Lock()

    # -- Device management --------------------------------------------------

    def start_device(self, ip: str, hostname: str = "", vendor: str = "",
                     mac_address: str | None = None, site_id: int | None = None,
                     device_id: int | None = None) -> MonitoredDevice:
        """Add a device to the monitoring registry and ensure the loop is running."""
        with self._lock:
            if ip in self._devices:
                logger.info("monitor_device_exists ip=%s", ip)
                return self._devices[ip]
            dev = MonitoredDevice(
                ip=ip, hostname=hostname or f"device-{ip.replace('.', '-')}",
                vendor=vendor, mac_address=mac_address, site_id=site_id,
                device_id=device_id, monitoring_since=time.time(),
            )
            self._devices[ip] = dev
            logger.info("monitor_device_started ip=%s device_id=%s interval_seconds=%s", ip, device_id, PING_INTERVAL)
        self._ensure_loop()
        self._event.set()
        # Initialize DB counters and set initial last_status_change
        self._init_device_db_state(dev)
        return dev

    def stop_device(self, ip: str) -> bool:
        """Remove a device from monitoring. Returns True if it was being monitored."""
        with self._lock:
            removed = self._devices.pop(ip, None)
        if removed:
            self._event.set()
            return True
        return False

    def start_all(self, devices: list[dict[str, Any]]) -> int:
        """Add multiple devices at once. Returns count of newly added."""
        added = 0
        new_devs: list[MonitoredDevice] = []
        with self._lock:
            for d in devices:
                ip = d.get("ip_address") or d.get("ip")
                if not ip or ip in self._devices:
                    continue
                dev = MonitoredDevice(
                    ip=ip,
                    hostname=d.get("hostname") or d.get("dns_hostname") or f"device-{ip.replace('.', '-')}",
                    vendor=d.get("vendor") or d.get("vendor_name") or "",
                    mac_address=d.get("mac_address") or d.get("mac"),
                    site_id=d.get("site_id"),
                    device_id=d.get("device_id"),
                    monitoring_since=time.time(),
                )
                self._devices[ip] = dev
                new_devs.append(dev)
                added += 1
        if added > 0:
            self._ensure_loop()
            self._event.set()
            # Initialize DB state for each newly added device
            for dev in new_devs:
                self._init_device_db_state(dev)
        return added

    def stop_all(self) -> int:
        """Stop monitoring all devices. Returns count removed."""
        with self._lock:
            count = len(self._devices)
            self._devices.clear()
        if count > 0:
            self._event.set()
        return count

    def shutdown(self) -> None:
        """Stop the monitor loop and release its shared ping executor."""
        self._stop_event.set()
        self._event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5.0)
        self._thread = None
        with self._executor_lock:
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=True)
        self._metric_batch_stop.set()
        self._metric_batch_event.set()
        self._metric_batch_thread.join(timeout=5.0)
        self._flush_metric_batch()

    def get_device(self, ip: str) -> MonitoredDevice | None:
        with self._lock:
            return self._devices.get(ip)

    def get_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [d.to_dict() for d in self._devices.values()]

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._devices)
            up = sum(1 for d in self._devices.values() if d.status == "up")
            down = sum(1 for d in self._devices.values() if d.status == "down")
            unknown = total - up - down
        return {
            "total_monitored": total,
            "up": up,
            "down": down,
            "unknown": unknown,
            "loop_running": self._thread is not None and self._thread.is_alive(),
        }

    def restore_enabled_devices(self) -> int:
        """Restore persisted ICMP-enabled devices once at application startup."""
        from backend.database.session import SessionLocal
        from backend.models import Device
        db = SessionLocal()
        try:
            devices = db.query(Device).filter(Device.deleted_at.is_(None), Device.monitoring_status.is_(True)).all()
            return self.start_all([{"device_id": d.id, "ip_address": d.ip_address, "hostname": d.hostname, "site_id": d.site_id} for d in devices])
        finally:
            db.close()

    # -- Background loop ----------------------------------------------------

    def _ensure_loop(self) -> None:
        """Start the background ping loop if not already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        with self._executor_lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=PING_MAX_WORKERS,
                    thread_name_prefix="mon-ping",
                )
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="monitor-engine")
        self._thread.start()

    def _loop(self) -> None:
        """Main monitoring loop: ping all devices every PING_INTERVAL seconds."""
        while not self._stop_event.is_set():
            with self._lock:
                ips = list(self._devices.keys())

            if not ips:
                # No devices to monitor — wait for new ones
                self._stop_event.wait(2.0)
                continue

            cycle_start = time.time()

            # Ping all devices concurrently using the engine-lifetime executor.
            with self._executor_lock:
                executor = self._executor
            if executor is None:
                break
            futures = {executor.submit(self._ping_one, ip): ip for ip in ips}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass

            self._event.set()  # Wake SSE subscribers

            # Sleep remaining time in the cycle
            elapsed = time.time() - cycle_start
            sleep_time = max(0.1, PING_INTERVAL - elapsed)
            self._stop_event.wait(sleep_time)

    def _metric_batch_loop(self) -> None:
        while not self._metric_batch_stop.wait(METRIC_BATCH_INTERVAL):
            self._flush_metric_batch()

    def _queue_metric(self, device_id: int, latency: float | None, packet_loss: float, now: datetime, icmp_status: str) -> None:
        should_flush = False
        with self._metric_batch_lock:
            self._metric_batch.append((device_id, latency, packet_loss, now, icmp_status))
            should_flush = len(self._metric_batch) >= METRIC_BATCH_SIZE
        logger.debug("ICMP_METRIC_BATCH_QUEUED size=%s", len(self._metric_batch))
        if should_flush:
            self._flush_metric_batch()

    def _flush_metric_batch(self) -> None:
        with self._metric_batch_lock:
            if not self._metric_batch:
                return
            rows = self._metric_batch
            self._metric_batch = []
        started = time.perf_counter()
        try:
            from backend.database.session import SessionLocal
            from backend.models import Device, DeviceMetric
            db = SessionLocal()
            try:
                for device_id, latency, packet_loss, timestamp, icmp_status in rows:
                    db.add(DeviceMetric(device_id=device_id, latency=latency, packet_loss=packet_loss, created_at=timestamp))
                    device = db.query(Device).filter(Device.id == device_id).first()
                    if device and _should_advance_last_seen(device.last_icmp_attempt_at, timestamp):
                        device.last_icmp_attempt_at = timestamp
                        device.last_icmp_status = icmp_status
                        if packet_loss == 0.0 and _should_advance_last_seen(device.last_seen, timestamp):
                            device.last_seen = timestamp
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
            logger.info("ICMP_METRIC_BATCH_FLUSHED size=%s duration_ms=%.2f", len(rows), (time.perf_counter() - started) * 1000)
        except Exception as exc:
            with self._metric_batch_lock:
                self._metric_batch = rows + self._metric_batch
            logger.warning("ICMP_METRIC_BATCH_FAILED size=%s error=%s", len(rows), exc)

    def _cached_device_state(self, device_id: int) -> dict[str, Any] | None:
        with self._device_cache_lock:
            item = self._device_cache.get(device_id)
            if item is None:
                return None
            expires, state = item
            if expires <= time.monotonic():
                self._device_cache.pop(device_id, None)
                logger.debug("ICMP_DEVICE_CACHE_INVALIDATED device_id=%s", device_id)
                return None
            return dict(state)

    def _cache_device_state(self, state: dict[str, Any]) -> None:
        with self._device_cache_lock:
            if len(self._device_cache) >= DEVICE_CACHE_MAX_SIZE and state["id"] not in self._device_cache:
                oldest = min(self._device_cache, key=lambda key: self._device_cache[key][0])
                self._device_cache.pop(oldest, None)
            self._device_cache[state["id"]] = (time.monotonic() + DEVICE_CACHE_TTL, dict(state))

    def _invalidate_device_state(self, device_id: int) -> None:
        with self._device_cache_lock:
            self._device_cache.pop(device_id, None)
        logger.debug("ICMP_DEVICE_CACHE_INVALIDATED device_id=%s", device_id)

    def _ping_one(self, ip: str) -> None:
        """Ping a single device and update its status."""
        with self._lock:
            dev = self._devices.get(ip)
        if not dev:
            return

        reachable, rtt = _ping(ip)
        now = datetime.now(_IST).strftime("%Y-%m-%dT%H:%M:%S")

        with self._lock:
            dev = self._devices.get(ip)
            if not dev:
                return

            dev.total_pings += 1
            dev.last_check = now
            dev.last_rtt_ms = rtt

            # Determine previous status before updating
            prev_status = dev.status

            observed_status = "up" if reachable else "down"
            if reachable:
                dev.consecutive_successes += 1
                dev.consecutive_failures = 0
                dev.total_up += 1
            else:
                dev.consecutive_failures += 1
                dev.consecutive_successes = 0
                dev.total_down += 1

            # Do not flap on one lost/late ICMP reply. Confirm transitions.
            if reachable and (dev.status in ("unknown", "down") and dev.consecutive_successes >= STATUS_CONFIRMATION_SUCCESSES):
                dev.status = "up"
            elif not reachable and (dev.status in ("unknown", "up") and dev.consecutive_failures >= STATUS_CONFIRMATION_FAILURES):
                dev.status = "down"

            logger.info("ping ip=%s observed=%s stable=%s rtt_ms=%s failures=%s successes=%s return_reason=%s",
                        ip, observed_status, dev.status, rtt, dev.consecutive_failures,
                        dev.consecutive_successes, "reply" if reachable else "timeout_or_error")

            # Append to history (capped)
            dev.history.append({
                "time": now,
                "status": dev.status,
                "rtt_ms": rtt,
            })
            if len(dev.history) > MAX_HISTORY:
                dev.history = dev.history[-MAX_HISTORY:]

        # ---- Persist to DB (outside the lock to avoid blocking) ----
        if dev.device_id is not None:
            self._persist_ping_result(dev, prev_status, reachable, rtt)

    def wait_for_update(self, timeout: float = 2.0) -> bool:
        """Block until new monitoring data is available or timeout. Used by SSE."""
        result = self._event.wait(timeout)
        self._event.clear()
        return result

    # -- DB persistence -----------------------------------------------------

    # Map in-memory status → DB status string (matches monitoring.py convention)
    _STATUS_MAP = {"up": "online", "down": "offline", "unknown": "unknown"}

    def _init_device_db_state(self, dev: MonitoredDevice) -> None:
        """Load initial DB state (uptime/downtime counters) for a device."""
        if dev.device_id is None:
            return
        try:
            from backend.database.session import SessionLocal
            from backend.models import Device
        except Exception:
            return

        db = SessionLocal()
        try:
            device = db.query(Device).filter(Device.id == dev.device_id).first()
            if not device:
                return
            with self._lock:
                dev.uptime_seconds = device.uptime_seconds or 0
                dev.downtime_seconds = device.downtime_seconds or 0
                dev.last_status_change = (
                    device.last_status_change.isoformat() if device.last_status_change else None
                )
        except Exception as exc:
            logger.warning("Failed to load DB state for %s: %s", dev.ip, exc)
        finally:
            db.close()

    def _persist_ping_result(
        self,
        dev: MonitoredDevice,
        prev_status: str,
        reachable: bool,
        rtt: float | None,
    ) -> None:
        """Persist a single ping result to the database.

        Creates a DeviceMetric row for every ping and, when the status
        transitions, a DeviceStatusHistory row + updates the device's
        cumulative uptime / downtime counters.
        """
        try:
            from backend.database.session import SessionLocal
            from backend.models import Alert, Device, DeviceMetric, DeviceStatusHistory
        except Exception:
            return  # DB not available — skip silently

        db = SessionLocal()
        try:
            now = _icmp_db_now()
            cached = self._cached_device_state(dev.device_id)
            if cached is not None:
                logger.debug("ICMP_DEVICE_CACHE_HIT device_id=%s", dev.device_id)
                device_id = cached["id"]
                db_status = cached["status"]
                hostname = cached["hostname"]
                ip_address = cached["ip_address"]
                device = None
            else:
                logger.debug("ICMP_DEVICE_CACHE_MISS device_id=%s", dev.device_id)
                device = db.query(Device).filter(Device.id == dev.device_id).first()
                if not device:
                    return
                device_id = device.id
                db_status = device.status
                hostname = device.hostname
                ip_address = device.ip_address
                self._cache_device_state({"id": device.id, "status": device.status, "hostname": device.hostname, "ip_address": device.ip_address})

            # A newly started monitor begins in memory as ``unknown``. Use the
            # persisted device state as the transition baseline so a restart
            # does not create false ``unknown -> online`` events.
            db_new_status = self._STATUS_MAP.get(dev.status, "unknown")
            db_old_status = db_status if db_status in {"online", "offline"} else self._STATUS_MAP.get(prev_status, "unknown")

            # A cached steady-state hit is safe; a possible transition must
            # use the current durable row before changing status or alerts.
            if cached is not None and db_old_status != db_new_status:
                device = db.query(Device).filter(Device.id == dev.device_id).first()
                if not device:
                    self._invalidate_device_state(dev.device_id)
                    return
                db_old_status = device.status if device.status in {"online", "offline"} else self._STATUS_MAP.get(prev_status, "unknown")
                hostname, ip_address = device.hostname, device.ip_address

            if db_new_status == "unknown" or db_old_status != db_new_status:
                if device is None:
                    device = db.query(Device).filter(Device.id == dev.device_id).first()
                if not device:
                    self._invalidate_device_state(dev.device_id)
                    return
                db.add(DeviceMetric(
                    device_id=device.id,
                    latency=rtt,
                    packet_loss=0.0 if reachable else 100.0,
                    created_at=now,
                ))

            if device is None and db_new_status != "unknown":
                device = db.query(Device).filter(Device.id == dev.device_id).first()
            if device is not None and (db_new_status == "unknown" or db_old_status != db_new_status) and _should_advance_last_seen(device.last_icmp_attempt_at, now):
                device.last_icmp_attempt_at = now
                device.last_icmp_status = "reachable" if reachable else "unreachable"

            # Keep last_seen current for every successful ping, not only when
            # the device changes state.
            if reachable:
                device.last_seen = now

            # The monitor needs two consecutive results to confirm a state.
            # Do not turn that warm-up value into a database transition (for
            # example, an existing online device must not become unknown).
            if db_new_status == "unknown":
                db.commit()
                return

            if db_old_status == db_new_status:
                db.close()
                self._queue_metric(device_id, rtt, 0.0 if reachable else 100.0, now, "reachable" if reachable else "unreachable")
                return

            self._flush_metric_batch()
            logger.info("ICMP_TRANSITION_IMMEDIATE_COMMIT device_id=%s status=%s", device_id, db_new_status)

            if db_old_status != db_new_status:
                # Accumulate time spent in the previous status
                if device.last_status_change:
                    elapsed = int((now - device.last_status_change).total_seconds())
                    if db_old_status == "online":
                        device.uptime_seconds = (device.uptime_seconds or 0) + elapsed
                    elif db_old_status == "offline":
                        device.downtime_seconds = (device.downtime_seconds or 0) + elapsed

                # ``unknown -> known`` establishes a baseline, rather than a
                # real up/down transition, so keep it out of the history.
                if db_old_status != "unknown":
                    db.add(DeviceStatusHistory(
                        device_id=device.id,
                        old_status=db_old_status,
                        new_status=db_new_status,
                        change_reason="Realtime ICMP check",
                    ))

                device.status = db_new_status
                device.last_status_change = now

                # Sync cumulative counters back to the in-memory model
                with self._lock:
                    dev.uptime_seconds = device.uptime_seconds or 0
                    dev.downtime_seconds = device.downtime_seconds or 0
                    dev.last_status_change = now.isoformat()

                # Create a critical alert when device goes offline
                if db_new_status == "offline":
                    from backend.services.alerting import create_offline_alert
                    create_offline_alert(db, device.id, device.hostname, device.ip_address)

                self._cache_device_state({"id": device.id, "status": device.status, "hostname": device.hostname, "ip_address": device.ip_address})

            db.commit()
        except Exception as exc:
            logger.warning("DB persist failed for %s: %s", dev.ip, exc)
            db.rollback()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_engine: MonitorEngine | None = None


def get_engine() -> MonitorEngine:
    """Return the singleton MonitorEngine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = MonitorEngine()
    return _engine
