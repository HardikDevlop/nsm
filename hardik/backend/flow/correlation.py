from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import text

from .models import NormalizedFlow


@dataclass(frozen=True, slots=True)
class DeviceMatch:
    device_id: int
    device_name: str | None


@dataclass(frozen=True, slots=True)
class InterfaceMatch:
    if_index: int
    name: str | None


class FlowCorrelationResolver:
    """Resolve flow exporter/interface identifiers against persisted SNMP data."""

    def __init__(self, ttl_seconds: float = 300.0, max_entries: int = 4096) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._devices: dict[str, tuple[float, DeviceMatch | None]] = {}
        self._interfaces: dict[tuple[int, int], tuple[float, InterfaceMatch | None]] = {}

    def correlate(self, db: Any, flows: Iterable[NormalizedFlow]) -> None:
        batch = list(flows)
        devices = {flow.exporter_ip: self._device(db, flow.exporter_ip) for flow in batch}
        for device in {match for match in devices.values() if match is not None}:
            self._load_interfaces(db, device.device_id, {
                index for flow in batch
                for index in (flow.input_interface_id, flow.output_interface_id)
                if devices[flow.exporter_ip] == device and index is not None
            })

        for flow in batch:
            device = devices[flow.exporter_ip]
            flow.device_id = device.device_id if device else None
            correlation = {
                "device_name": device.device_name if device else None,
                "input_ifindex": flow.input_interface_id,
                "input_interface_name": self._interface_name(device, flow.input_interface_id),
                "output_ifindex": flow.output_interface_id,
                "output_interface_name": self._interface_name(device, flow.output_interface_id),
            }
            flow.raw_fields.setdefault("correlation", {}).update(correlation)

    def correlate_counters(self, db: Any, counters: Iterable[Any]) -> None:
        batch = list(counters)
        devices = {counter.exporter_ip: self._device(db, counter.exporter_ip) for counter in batch}
        for device in {match for match in devices.values() if match is not None}:
            self._load_interfaces(db, device.device_id, {
                counter.if_index for counter in batch
                if devices[counter.exporter_ip] == device
            })
        for counter in batch:
            device = devices[counter.exporter_ip]
            counter.device_id = device.device_id if device else None
            match = self._cached(self._interfaces, (device.device_id, counter.if_index)) if device else None
            counter.interface_name = None if match in (_MISSING, None) else match.name
            counter.raw_fields.setdefault("correlation", {}).update({
                "device_name": device.device_name if device else None,
                "ifindex": counter.if_index,
                "interface_name": counter.interface_name,
            })

    def _device(self, db: Any, exporter_ip: str) -> DeviceMatch | None:
        cached = self._cached(self._devices, exporter_ip)
        if cached is not _MISSING:
            return cached
        rows = db.execute(text(
            "SELECT id, hostname FROM devices "
            "WHERE ip_address = :exporter_ip AND deleted_at IS NULL LIMIT 2"
        ), {"exporter_ip": exporter_ip}).mappings().all()
        match = DeviceMatch(int(rows[0]["id"]), rows[0].get("hostname")) if len(rows) == 1 else None
        self._put(self._devices, exporter_ip, match)
        return match

    def _load_interfaces(self, db: Any, device_id: int, indexes: set[int]) -> None:
        missing = {index for index in indexes if self._cached(self._interfaces, (device_id, index)) is _MISSING}
        if not missing:
            return
        rows = db.execute(text(
            "SELECT if_index, name FROM latest_interface WHERE device_id = :device_id "
            "AND if_index = ANY(:if_indexes) "
            "UNION ALL "
            "SELECT di.if_index, di.name FROM device_interfaces di "
            "WHERE di.device_id = :device_id AND di.if_index = ANY(:if_indexes) "
            "AND NOT EXISTS (SELECT 1 FROM latest_interface li "
            "WHERE li.device_id = di.device_id AND li.if_index = di.if_index)"
        ), {"device_id": device_id, "if_indexes": list(missing)}).mappings().all()
        by_index = {int(row["if_index"]): InterfaceMatch(int(row["if_index"]), row.get("name")) for row in rows}
        for index in missing:
            self._put(self._interfaces, (device_id, index), by_index.get(index))

    def _interface_name(self, device: DeviceMatch | None, if_index: int | None) -> str | None:
        if device is None or if_index is None:
            return None
        match = self._cached(self._interfaces, (device.device_id, if_index))
        return None if match in (_MISSING, None) else match.name

    def _cached(self, cache: dict[Any, tuple[float, Any]], key: Any) -> Any:
        item = cache.get(key)
        if item is None:
            return _MISSING
        expires_at, value = item
        if expires_at <= time.monotonic():
            cache.pop(key, None)
            return _MISSING
        return value

    def _put(self, cache: dict[Any, tuple[float, Any]], key: Any, value: Any) -> None:
        if len(cache) >= self.max_entries:
            cache.pop(next(iter(cache)))
        cache[key] = (time.monotonic() + self.ttl_seconds, value)


_MISSING = object()
