from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


@dataclass(slots=True)
class NormalizedFlow:
    exporter_ip: str
    protocol: str
    flow_start: datetime | None
    flow_end: datetime | None
    received_at: datetime
    device_id: int | None = None
    src_ip: str | None = None
    dst_ip: str | None = None
    src_port: int | None = None
    dst_port: int | None = None
    ip_protocol: int | None = None
    bytes: int = 0
    packets: int = 0
    input_interface_id: int | None = None
    output_interface_id: int | None = None
    observation_domain: str | None = None
    source_version: str | None = None
    sampling_rate: int | None = None
    raw_fields: dict[str, Any] = field(default_factory=dict)

    @property
    def record_hash(self) -> str:
        identity = "|".join(str(value) for value in (
            self.exporter_ip, self.protocol, self.observation_domain,
            self.flow_start.isoformat() if self.flow_start else None,
            self.flow_end.isoformat() if self.flow_end else None,
            self.src_ip, self.dst_ip, self.src_port, self.dst_port,
            self.ip_protocol, self.bytes, self.packets,
        ))
        return sha256(identity.encode("utf-8")).hexdigest()

    def validate(self) -> None:
        if not self.exporter_ip or self.protocol not in {"ipfix", "sflow"}:
            raise ValueError("invalid flow identity")
        if self.flow_start and self.flow_end and self.flow_end < self.flow_start:
            raise ValueError("flow_end precedes flow_start")
        if self.bytes < 0 or self.packets < 0:
            raise ValueError("flow counters cannot be negative")


def epoch_seconds(seconds: int, nanos: int = 0) -> datetime:
    return datetime.fromtimestamp(seconds + nanos / 1_000_000_000, tz=timezone.utc).replace(tzinfo=None)
