from __future__ import annotations

import ipaddress
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import NormalizedFlow, epoch_seconds


class FlowParseError(ValueError):
    pass


def _ip(value: bytes) -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise FlowParseError("invalid address field") from exc


def _u(data: bytes, offset: int, size: int) -> int:
    if offset < 0 or offset + size > len(data):
        raise FlowParseError("truncated flow record")
    return int.from_bytes(data[offset:offset + size], "big")


@dataclass(frozen=True, slots=True)
class IPFIXField:
    element_id: int
    length: int
    enterprise_id: int | None = None


@dataclass(frozen=True, slots=True)
class IPFIXTemplate:
    fields: tuple[IPFIXField, ...]
    options: bool = False
    scope_field_count: int = 0


class IPFIXParser:
    """Parse IPFIX v10 templates and data sets."""
    TEMPLATE_TTL_SECONDS = 1800.0

    def __init__(self, template_ttl_seconds: float = TEMPLATE_TTL_SECONDS):
        self.template_ttl_seconds = template_ttl_seconds
        self.templates: dict[tuple[str, int, int], tuple[IPFIXTemplate, float]] = {}
        self.options_templates: dict[tuple[str, int, int], tuple[IPFIXTemplate, float]] = {}
        self.sequence_state: dict[tuple[str, int], tuple[int, datetime, int]] = {}
        self.diagnostics: dict[str, int] = {
            "unknown_template": 0,
            "expired_template": 0,
            "template_withdrawal": 0,
            "malformed_set": 0,
            "sequence_gaps": 0,
        }

    def parse(self, payload: bytes, exporter_ip: str, received_at: datetime | None = None) -> list[NormalizedFlow]:
        if len(payload) < 16 or _u(payload, 0, 2) != 10:
            raise FlowParseError("invalid IPFIX header")
        packet_length = _u(payload, 2, 2)
        export_seconds = _u(payload, 4, 4)
        sequence_number = _u(payload, 8, 4)
        domain = _u(payload, 12, 4)
        if packet_length < 16 or packet_length > len(payload):
            raise FlowParseError("invalid IPFIX length")
        received = received_at or datetime.now(timezone.utc).replace(tzinfo=None)
        export_time = epoch_seconds(export_seconds)
        sequence = self._sequence_status(exporter_ip, domain, sequence_number, export_time, 0, update=False)
        cursor, output, data_records = 16, [], 0
        while cursor + 4 <= packet_length:
            set_id, length = _u(payload, cursor, 2), _u(payload, cursor + 2, 2)
            if length < 4 or cursor + length > packet_length:
                self.diagnostics["malformed_set"] += 1
                raise FlowParseError("invalid IPFIX set length")
            body = payload[cursor + 4:cursor + length]
            if set_id == 2:
                self._parse_templates(exporter_ip, domain, body, options=False)
            elif set_id == 3:
                self._parse_templates(exporter_ip, domain, body, options=True)
            elif set_id >= 256:
                template = self._template(exporter_ip, domain, set_id, options=False)
                if template is None:
                    if self._template(exporter_ip, domain, set_id, options=True) is not None:
                        cursor += length
                        continue
                    self.diagnostics["unknown_template"] += 1
                    cursor += length
                    continue
                records = self._data_records(body, template, exporter_ip, received, export_time, domain, sequence)
                output.extend(records)
                data_records += len(records)
            cursor += length
        if data_records:
            self._sequence_status(exporter_ip, domain, sequence_number, export_time, data_records)
        return output

    def _parse_templates(self, exporter_ip: str, domain: int, body: bytes, *, options: bool) -> None:
        cursor = 0
        while cursor + 4 <= len(body):
            template_id, field_count = _u(body, cursor, 2), _u(body, cursor + 2, 2)
            cursor += 4
            if field_count == 0:
                self._withdraw(exporter_ip, domain, template_id, options)
                continue
            scope_count = 0
            if options:
                if cursor + 2 > len(body):
                    raise FlowParseError("truncated IPFIX options template")
                scope_count = _u(body, cursor, 2)
                cursor += 2
            if field_count > 128:
                raise FlowParseError("invalid IPFIX template field count")
            fields: list[IPFIXField] = []
            for _ in range(field_count):
                if cursor + 4 > len(body):
                    raise FlowParseError("truncated IPFIX template field")
                raw_id, field_length = _u(body, cursor, 2), _u(body, cursor + 2, 2)
                cursor += 4
                enterprise_id = None
                if raw_id & 0x8000:
                    if cursor + 4 > len(body):
                        raise FlowParseError("truncated IPFIX enterprise field")
                    enterprise_id = _u(body, cursor, 4)
                    cursor += 4
                fields.append(IPFIXField(raw_id & 0x7FFF, field_length, enterprise_id))
            template = IPFIXTemplate(tuple(fields), options, scope_count)
            cache = self.options_templates if options else self.templates
            cache[(exporter_ip, domain, template_id)] = (template, time.monotonic())

    def _withdraw(self, exporter_ip: str, domain: int, template_id: int, options: bool) -> None:
        cache = self.options_templates if options else self.templates
        if template_id == 0:
            keys = [key for key in cache if key[:2] == (exporter_ip, domain)]
            for key in keys:
                cache.pop(key, None)
        else:
            cache.pop((exporter_ip, domain, template_id), None)
        self.diagnostics["template_withdrawal"] += 1

    def _template(self, exporter_ip: str, domain: int, template_id: int, *, options: bool) -> IPFIXTemplate | None:
        cache = self.options_templates if options else self.templates
        key = (exporter_ip, domain, template_id)
        entry = cache.get(key)
        if entry is None:
            return None
        template, last_seen = entry
        if time.monotonic() - last_seen > self.template_ttl_seconds:
            cache.pop(key, None)
            self.diagnostics["expired_template"] += 1
            return None
        return template

    def _data_records(self, body: bytes, template: IPFIXTemplate, exporter_ip: str, received: datetime, export_time: datetime, domain: int, sequence: dict[str, Any]) -> list[NormalizedFlow]:
        output: list[NormalizedFlow] = []
        cursor = 0
        while cursor < len(body):
            values: dict[int, int | bytes] = {}
            metadata: list[dict[str, Any]] = []
            record_start = cursor
            for field in template.fields:
                raw, cursor = self._field_value(body, cursor, field.length)
                if raw is None:
                    return output
                value = self._decode_field(field.element_id, raw)
                values[field.element_id] = value
                metadata.append({"element_id": field.element_id, "length": field.length, "enterprise_id": field.enterprise_id, "value": raw.hex() if field.enterprise_id is not None else None})
            if cursor == record_start:
                break
            start = self._timestamp(values, 152, 150, 154, 156)
            end = self._timestamp(values, 153, 151, 155, 157)
            quality = "sampled" if 34 in values or 305 in values else "unknown"
            raw_fields: dict[str, Any] = {"quality": quality, "ipfix": {
                "export_time": export_time.isoformat(), "sequence_number": sequence["sequence_number"],
                "observation_domain_id": domain, "sequence": sequence, "fields": metadata,
            }}
            unknown = [item for item in metadata if item["element_id"] not in {1, 2, 4, 7, 8, 10, 11, 12, 14, 27, 28, 34, 35, 150, 151, 152, 153, 154, 155, 156, 157, 305}]
            if unknown:
                raw_fields["ipfix"]["unknown_information_elements"] = unknown
            output.append(NormalizedFlow(
                exporter_ip=exporter_ip, protocol="ipfix", source_version="10", observation_domain=str(domain),
                flow_start=start, flow_end=end, received_at=received,
                src_ip=self._address(values.get(8) if values.get(8) is not None else values.get(27)),
                dst_ip=self._address(values.get(12) if values.get(12) is not None else values.get(28)),
                input_interface_id=self._number(values.get(10)), output_interface_id=self._number(values.get(14)),
                packets=self._number(values.get(2)) or 0, bytes=self._number(values.get(1)) or 0,
                src_port=self._number(values.get(7)), dst_port=self._number(values.get(11)),
                ip_protocol=self._number(values.get(4)), raw_fields=raw_fields,
            ))
        return output

    @staticmethod
    def _field_value(body: bytes, cursor: int, length: int) -> tuple[bytes | None, int]:
        if length == 65535:
            if cursor >= len(body):
                return None, cursor
            prefix = body[cursor]
            cursor += 1
            if prefix == 255:
                if cursor + 2 > len(body):
                    return None, cursor
                length = int.from_bytes(body[cursor:cursor + 2], "big")
                cursor += 2
            else:
                length = prefix
        if length < 0 or cursor + length > len(body):
            return None, cursor
        return body[cursor:cursor + length], cursor + length

    @staticmethod
    def _decode_field(element_id: int, raw: bytes) -> int | bytes:
        if element_id in (8, 12) and len(raw) == 4:
            return raw
        if element_id in (27, 28) and len(raw) == 16:
            return raw
        return int.from_bytes(raw, "big")

    @staticmethod
    def _address(value: int | bytes | None) -> str | None:
        return _ip(value) if isinstance(value, bytes) else None

    @staticmethod
    def _number(value: int | bytes | None) -> int | None:
        return value if isinstance(value, int) else None

    @staticmethod
    def _timestamp(values: dict[int, int | bytes], milliseconds: int, seconds: int, microseconds: int, nanoseconds: int) -> datetime | None:
        for element_id, divisor in ((milliseconds, 1000), (seconds, 1), (microseconds, 1_000_000), (nanoseconds, 1_000_000_000)):
            value = values.get(element_id)
            if isinstance(value, int):
                return datetime.fromtimestamp(value / divisor, tz=timezone.utc).replace(tzinfo=None)
        return None

    def _sequence_status(self, exporter_ip: str, domain: int, sequence_number: int, export_time: datetime, data_records: int, *, update: bool = True) -> dict[str, Any]:
        key = (exporter_ip, domain)
        previous = self.sequence_state.get(key)
        status = "initial"
        lost = 0
        if previous is not None:
            previous_sequence, previous_time, previous_records = previous
            delta = (sequence_number - previous_sequence) & 0xFFFFFFFF
            if export_time < previous_time:
                status = "restart"
            elif previous_sequence == 0xFFFFFFFF and sequence_number == 0:
                status = "wrap"
            elif delta == 0:
                status = "duplicate"
            elif delta == previous_records:
                status = "in_order"
            elif delta < 0x80000000 and delta > previous_records:
                status = "gap"
                lost = delta - previous_records
                self.diagnostics["sequence_gaps"] += 1
            else:
                status = "reset"
        if update:
            self.sequence_state[key] = (sequence_number, export_time, data_records)
        return {"status": status, "gap": status == "gap", "lost": lost, "sequence_number": sequence_number}


@dataclass(slots=True)
class SFlowCounterSample:
    exporter_ip: str
    agent_address: str
    sub_agent_id: int
    sequence_number: int
    if_index: int
    if_type: int
    if_speed: int
    if_direction: int
    if_status: int
    if_in_octets: int
    if_in_ucast_pkts: int
    if_in_multicast_pkts: int
    if_in_broadcast_pkts: int
    if_in_discards: int
    if_in_errors: int
    if_out_octets: int
    if_out_ucast_pkts: int
    if_out_multicast_pkts: int
    if_out_broadcast_pkts: int
    if_out_discards: int
    if_out_errors: int
    observed_at: datetime
    device_id: int | None = None
    interface_name: str | None = None
    raw_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SFlowParseResult:
    flows: list[NormalizedFlow]
    counters: list[SFlowCounterSample]


class SFlowParser:
    """Parse sFlow v5 datagrams and Ethernet/IPv4/IPv6 flow samples."""

    def __init__(self):
        self._sequence_state: dict[tuple[str, int], tuple[int, int]] = {}

    def parse(self, payload: bytes, exporter_ip: str, received_at: datetime | None = None) -> list[NormalizedFlow]:
        return self.parse_datagram(payload, exporter_ip, received_at).flows

    def parse_datagram(self, payload: bytes, exporter_ip: str, received_at: datetime | None = None) -> SFlowParseResult:
        if len(payload) < 28 or _u(payload, 0, 4) != 5:
            raise FlowParseError("invalid sFlow v5 header")
        address_type = _u(payload, 4, 4)
        address_size = 4 if address_type == 1 else 16 if address_type == 2 else 0
        if not address_size or len(payload) < 16 + address_size:
            raise FlowParseError("invalid sFlow agent address")
        agent = _ip(payload[8:8 + address_size])
        cursor = 8 + address_size
        if cursor + 16 > len(payload):
            raise FlowParseError("truncated sFlow header")
        sub_agent, datagram_sequence, agent_uptime, sample_count = struct.unpack_from("!IIII", payload, cursor)
        cursor += 16
        received = received_at or datetime.now(timezone.utc).replace(tzinfo=None)
        sequence = self._sequence_status(agent, sub_agent, datagram_sequence, agent_uptime)
        output: list[NormalizedFlow] = []
        counters: list[SFlowCounterSample] = []
        for _ in range(sample_count):
            if cursor + 8 > len(payload):
                raise FlowParseError("truncated sFlow sample header")
            sample_format, sample_length = _u(payload, cursor, 4), _u(payload, cursor + 4, 4)
            cursor += 8
            if sample_length > len(payload) - cursor:
                raise FlowParseError("invalid sFlow sample length")
            sample = payload[cursor:cursor + sample_length]
            cursor += sample_length
            if sample_format == 1:
                output.extend(self._flow_sample(sample, exporter_ip, agent, sub_agent, datagram_sequence, agent_uptime, sample_count, sequence, received))
            elif sample_format == 2:
                counters.extend(self._counter_sample(sample, exporter_ip, agent, sub_agent, received))
        return SFlowParseResult(output, counters)

    def _sequence_status(self, agent: str, sub_agent: int, sequence: int, uptime: int) -> dict[str, Any]:
        key = (agent, sub_agent)
        previous = self._sequence_state.get(key)
        self._sequence_state[key] = (sequence, uptime)
        if previous is None:
            return {"status": "initial", "gap": False, "lost": 0}
        previous_sequence, previous_uptime = previous
        if uptime < previous_uptime:
            return {"status": "restart", "gap": False, "lost": 0}
        if previous_sequence == 0xFFFFFFFF and sequence == 0:
            return {"status": "wrap", "gap": False, "lost": 0}
        delta = (sequence - previous_sequence) & 0xFFFFFFFF
        if delta == 0:
            return {"status": "duplicate", "gap": False, "lost": 0}
        if delta == 1:
            return {"status": "in_order", "gap": False, "lost": 0}
        if delta < 0x80000000:
            return {"status": "gap", "gap": True, "lost": delta - 1}
        return {"status": "wrap", "gap": False, "lost": 0}

    def _flow_sample(self, sample: bytes, exporter_ip: str, agent: str, sub_agent: int, datagram_sequence: int, agent_uptime: int, sample_count: int, sequence: dict[str, Any], received: datetime) -> list[NormalizedFlow]:
        # flow_sample: seq, source_id, sampling_rate, sample_pool, drops,
        # input, output, record_count, followed by flow records.
        if len(sample) < 32:
            raise FlowParseError("truncated sFlow flow sample")
        sample_sequence, source_id, sampling_rate, sample_pool, drops, input_if, output_if, record_count = struct.unpack_from("!IIIIIIII", sample, 0)
        cursor, output = 32, []
        last_flow: NormalizedFlow | None = None
        for _ in range(record_count):
            if cursor + 8 > len(sample):
                raise FlowParseError("truncated sFlow flow record header")
            record_format, record_length = _u(sample, cursor, 4), _u(sample, cursor + 4, 4)
            cursor += 8
            if record_length > len(sample) - cursor:
                raise FlowParseError("invalid sFlow flow record length")
            record = sample[cursor:cursor + record_length]
            cursor += record_length
            if record_format == 1001:
                if len(record) >= 16 and last_flow is not None:
                    source_vlan, _source_priority, destination_vlan, _destination_priority = struct.unpack_from("!IIII", record, 0)
                    last_flow.raw_fields["sflow"]["source_vlan"] = source_vlan or None
                    last_flow.raw_fields["sflow"]["destination_vlan"] = destination_vlan or None
                continue
            if record_format != 1:
                continue
            if len(record) < 16:
                raise FlowParseError("truncated sFlow sampled packet header")
            protocol, frame_length, _stripped, header_length = struct.unpack_from("!IIII", record, 0)
            if protocol != 1 or header_length > len(record) - 16:
                raise FlowParseError("unsupported sFlow packet header")
            packet = record[16:16 + header_length]
            parsed = self._ethernet_ip(packet)
            if not parsed:
                continue
            src_ip, dst_ip, src_port, dst_port, ip_protocol = parsed
            flow = NormalizedFlow(
                exporter_ip=exporter_ip, protocol="sflow", source_version="5",
                flow_start=received, flow_end=received, received_at=received,
                src_ip=src_ip, dst_ip=dst_ip, src_port=src_port, dst_port=dst_port,
                ip_protocol=ip_protocol, bytes=frame_length, packets=1,
                input_interface_id=input_if, output_interface_id=output_if,
                sampling_rate=sampling_rate, observation_domain=str(source_id),
                raw_fields={"quality": "packet_sample", "sflow": {
                    "agent_address": agent, "sub_agent_id": sub_agent,
                    "datagram_sequence": datagram_sequence, "agent_uptime": agent_uptime,
                    "sample_count": sample_count, "sample_sequence": sample_sequence,
                    "sampling_rate": sampling_rate, "sample_pool": sample_pool,
                    "drops": drops, "sampled_packet_length": frame_length,
                    "source_mac": self._mac(packet[6:12]),
                    "destination_mac": self._mac(packet[0:6]),
                    "vlan_id": self._vlan(packet), "sequence": sequence,
                }},
            )
            output.append(flow)
            last_flow = flow
        return output

    def _counter_sample(self, sample: bytes, exporter_ip: str, agent: str, sub_agent: int, received: datetime) -> list[SFlowCounterSample]:
        if len(sample) < 12:
            raise FlowParseError("truncated sFlow counter sample")
        sequence, _source_id, record_count = struct.unpack_from("!III", sample, 0)
        cursor, output = 12, []
        for _ in range(record_count):
            if cursor + 8 > len(sample):
                raise FlowParseError("truncated sFlow counter record header")
            record_format, record_length = _u(sample, cursor, 4), _u(sample, cursor + 4, 4)
            cursor += 8
            if record_length > len(sample) - cursor:
                raise FlowParseError("invalid sFlow counter record length")
            record = sample[cursor:cursor + record_length]
            cursor += record_length
            if record_format != 1:
                continue
            if len(record) < 84:
                raise FlowParseError("truncated sFlow generic interface counter")
            values = struct.unpack_from("!IIQIIQIIIIIQIIIIII", record, 0)
            output.append(SFlowCounterSample(
                exporter_ip=exporter_ip, agent_address=agent, sub_agent_id=sub_agent,
                sequence_number=sequence, if_index=values[0], if_type=values[1], if_speed=values[2],
                if_direction=values[3], if_status=values[4], if_in_octets=values[5],
                if_in_ucast_pkts=values[6], if_in_multicast_pkts=values[7], if_in_broadcast_pkts=values[8],
                if_in_discards=values[9], if_in_errors=values[10], if_out_octets=values[11],
                if_out_ucast_pkts=values[12], if_out_multicast_pkts=values[13], if_out_broadcast_pkts=values[14],
                if_out_discards=values[15], if_out_errors=values[16], observed_at=received,
                raw_fields={"quality": "counter_sample", "sflow": {"record_type": "generic_interface"}},
            ))
        return output

    @staticmethod
    def _mac(value: bytes) -> str | None:
        return ":".join(f"{part:02x}" for part in value) if len(value) == 6 else None

    @staticmethod
    def _vlan(packet: bytes) -> int | None:
        if len(packet) >= 18 and int.from_bytes(packet[12:14], "big") in (0x8100, 0x88A8, 0x9100):
            return int.from_bytes(packet[14:16], "big") & 0x0FFF
        return None

    @staticmethod
    def _ethernet_ip(packet: bytes) -> tuple[str, str, int | None, int | None, int] | None:
        if len(packet) < 14:
            return None
        ether_type = int.from_bytes(packet[12:14], "big")
        offset = 14
        if ether_type == 0x8100 and len(packet) >= 18:
            ether_type, offset = int.from_bytes(packet[16:18], "big"), 18
        if ether_type == 0x0800:
            if len(packet) < offset + 20:
                return None
            ihl = (packet[offset] & 0x0F) * 4
            if ihl < 20 or len(packet) < offset + ihl:
                return None
            protocol = packet[offset + 9]
            src, dst = str(ipaddress.ip_address(packet[offset + 12:offset + 16])), str(ipaddress.ip_address(packet[offset + 16:offset + 20]))
            ports = SFlowParser._ports(packet[offset + ihl:], protocol)
            return src, dst, ports[0], ports[1], protocol
        if ether_type == 0x86DD and len(packet) >= offset + 40:
            protocol = packet[offset + 6]
            src, dst = str(ipaddress.ip_address(packet[offset + 8:offset + 24])), str(ipaddress.ip_address(packet[offset + 24:offset + 40]))
            ports = SFlowParser._ports(packet[offset + 40:], protocol)
            return src, dst, ports[0], ports[1], protocol
        return None

    @staticmethod
    def _ports(payload: bytes, protocol: int) -> tuple[int | None, int | None]:
        if protocol in (6, 17) and len(payload) >= 4:
            return _u(payload, 0, 2), _u(payload, 2, 2)
        return None, None
