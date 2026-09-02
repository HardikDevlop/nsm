from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass
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


@dataclass(slots=True)
class NetFlowTemplate:
    fields: list[tuple[int, int]]


class NetFlowParser:
    """Parser for NetFlow v5 and v9 common fields."""

    def __init__(self):
        self.templates: dict[tuple[str, int], NetFlowTemplate] = {}

    def parse(self, payload: bytes, exporter_ip: str, received_at: datetime | None = None) -> list[NormalizedFlow]:
        if len(payload) < 4:
            raise FlowParseError("flow packet is too short")
        version = _u(payload, 0, 2)
        if version == 5:
            return self._v5(payload, exporter_ip, received_at)
        if version == 9:
            return self._v9(payload, exporter_ip, received_at)
        raise FlowParseError(f"unsupported NetFlow version {version}")

    def _v5(self, payload: bytes, exporter_ip: str, received_at: datetime | None) -> list[NormalizedFlow]:
        if len(payload) < 24:
            raise FlowParseError("truncated NetFlow v5 header")
        count = _u(payload, 2, 2)
        if count > 30 or len(payload) < 24 + count * 48:
            raise FlowParseError("invalid NetFlow v5 record count")
        unix_secs, unix_nsecs, sys_uptime = _u(payload, 8, 4), _u(payload, 12, 4), _u(payload, 16, 4)
        received = received_at or datetime.now(timezone.utc).replace(tzinfo=None)
        export_time = epoch_seconds(unix_secs, unix_nsecs)
        output = []
        for index in range(count):
            offset = 24 + index * 48
            first, last = _u(payload, offset + 24, 4), _u(payload, offset + 28, 4)
            start = export_time - timedelta(milliseconds=max(0, sys_uptime - first))
            end = export_time - timedelta(milliseconds=max(0, sys_uptime - last))
            output.append(NormalizedFlow(
                exporter_ip=exporter_ip, protocol="netflow", source_version="5",
                flow_start=start, flow_end=max(start, end), received_at=received,
                src_ip=_ip(payload[offset:offset + 4]), dst_ip=_ip(payload[offset + 4:offset + 8]),
                input_interface_id=_u(payload, offset + 12, 2), output_interface_id=_u(payload, offset + 14, 2),
                packets=_u(payload, offset + 16, 4), bytes=_u(payload, offset + 20, 4),
                src_port=_u(payload, offset + 32, 2), dst_port=_u(payload, offset + 34, 2),
                ip_protocol=_u(payload, offset + 38, 1),
            ))
        return output

    def _v9(self, payload: bytes, exporter_ip: str, received_at: datetime | None) -> list[NormalizedFlow]:
        if len(payload) < 20:
            raise FlowParseError("truncated NetFlow v9 header")
        count, sys_uptime, unix_secs, source_id = _u(payload, 2, 2), _u(payload, 4, 4), _u(payload, 8, 4), _u(payload, 16, 4)
        if count > 4096:
            raise FlowParseError("NetFlow v9 count exceeds packet limit")
        received = received_at or datetime.now(timezone.utc).replace(tzinfo=None)
        export_time = epoch_seconds(unix_secs)
        cursor, output = 20, []
        while cursor + 4 <= len(payload):
            flowset_id, length = _u(payload, cursor, 2), _u(payload, cursor + 2, 2)
            if length < 4 or cursor + length > len(payload):
                raise FlowParseError("invalid NetFlow v9 flowset length")
            body = payload[cursor + 4:cursor + length]
            if flowset_id in (0, 2):
                self._templates(exporter_ip, source_id, body)
            elif flowset_id >= 256:
                template = self.templates.get((exporter_ip, flowset_id)) or self.templates.get((exporter_ip, source_id))
                if template:
                    output.extend(self._data_records(body, template, exporter_ip, received, export_time, sys_uptime))
            cursor += length
        return output

    def _templates(self, exporter_ip: str, source_id: int, body: bytes) -> None:
        cursor = 0
        while cursor + 4 <= len(body):
            template_id, field_count = _u(body, cursor, 2), _u(body, cursor + 2, 2)
            cursor += 4
            if field_count > 128 or cursor + field_count * 4 > len(body):
                raise FlowParseError("invalid NetFlow v9 template")
            fields = [(_u(body, cursor + i * 4, 2), _u(body, cursor + i * 4 + 2, 2)) for i in range(field_count)]
            self.templates[(exporter_ip, template_id)] = NetFlowTemplate(fields)
            self.templates[(exporter_ip, source_id)] = NetFlowTemplate(fields)
            cursor += field_count * 4

    def _data_records(self, body: bytes, template: NetFlowTemplate, exporter_ip: str, received: datetime, export_time: datetime, sys_uptime: int) -> list[NormalizedFlow]:
        width = sum(size for _, size in template.fields)
        if not width:
            return []
        output = []
        for offset in range(0, len(body) - width + 1, width):
            values: dict[int, int | bytes] = {}
            cursor = offset
            for field_id, size in template.fields:
                raw = body[cursor:cursor + size]
                values[field_id] = raw if size in (4, 16) and field_id in (8, 12, 225, 226) else int.from_bytes(raw, "big")
                cursor += size
            first = int(values.get(22, sys_uptime))
            last = int(values.get(21, first))
            start = export_time - timedelta(milliseconds=max(0, sys_uptime - first))
            end = export_time - timedelta(milliseconds=max(0, sys_uptime - last))
            output.append(NormalizedFlow(
                exporter_ip=exporter_ip, protocol="netflow", source_version="9",
                flow_start=start, flow_end=max(start, end), received_at=received,
                src_ip=_ip(values[8]) if isinstance(values.get(8), bytes) else None,
                dst_ip=_ip(values[12]) if isinstance(values.get(12), bytes) else None,
                input_interface_id=values.get(10) if isinstance(values.get(10), int) else None,
                output_interface_id=values.get(14) if isinstance(values.get(14), int) else None,
                packets=int(values.get(2, 0)), bytes=int(values.get(1, 0)),
                src_port=int(values.get(7, 0)) or None, dst_port=int(values.get(11, 0)) or None,
                ip_protocol=int(values.get(4, 0)) or None,
            ))
        return output


class IPFIXParser:
    """IPFIX v10 parser sharing the NetFlow v9 template model."""

    def __init__(self):
        self.templates: dict[tuple[str, int], NetFlowTemplate] = {}

    def parse(self, payload: bytes, exporter_ip: str, received_at: datetime | None = None) -> list[NormalizedFlow]:
        if len(payload) < 16 or _u(payload, 0, 2) != 10:
            raise FlowParseError("invalid IPFIX header")
        length, domain = _u(payload, 2, 2), _u(payload, 12, 4)
        if length < 16 or length > len(payload):
            raise FlowParseError("invalid IPFIX length")
        parser = NetFlowParser()
        parser.templates = self.templates
        # IPFIX set IDs and timestamps differ, but template/data field encoding
        # is shared. Convert the header to the v9 shape for the common decoder.
        converted = struct.pack("!HHIIII", 9, 0, 0, 0, _u(payload, 8, 4), domain) + payload[16:length]
        result = parser._v9(converted, exporter_ip, received_at)
        self.templates = parser.templates
        for flow in result:
            flow.protocol, flow.source_version, flow.observation_domain = "ipfix", "10", str(domain)
        return result


class SFlowParser:
    """Parse sFlow v5 datagrams and Ethernet/IPv4/IPv6 flow samples."""

    def parse(self, payload: bytes, exporter_ip: str, received_at: datetime | None = None) -> list[NormalizedFlow]:
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
        _sub_agent, _sequence, _uptime, sample_count = struct.unpack_from("!IIII", payload, cursor)
        cursor += 16
        received = received_at or datetime.now(timezone.utc).replace(tzinfo=None)
        output: list[NormalizedFlow] = []
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
                output.extend(self._flow_sample(sample, agent, received))
        return output

    def _flow_sample(self, sample: bytes, exporter_ip: str, received: datetime) -> list[NormalizedFlow]:
        # flow_sample: seq, source_id, sampling_rate, sample_pool, drops,
        # input, output, record_count, followed by flow records.
        if len(sample) < 32:
            raise FlowParseError("truncated sFlow flow sample")
        sequence, source_id, sampling_rate, _pool, _drops, input_if, output_if, record_count = struct.unpack_from("!IIIIIIII", sample, 0)
        cursor, output = 32, []
        for _ in range(record_count):
            if cursor + 8 > len(sample):
                raise FlowParseError("truncated sFlow flow record header")
            record_format, record_length = _u(sample, cursor, 4), _u(sample, cursor + 4, 4)
            cursor += 8
            if record_length > len(sample) - cursor:
                raise FlowParseError("invalid sFlow flow record length")
            record = sample[cursor:cursor + record_length]
            cursor += record_length
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
                raw_fields={"sample_sequence": sequence, "drops": _drops},
            )
            output.append(flow)
        return output

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


class CompatibleVendorFlowParser:
    """Reuse NetFlow/IPFIX decoders for wire-compatible J-Flow/NetStream."""

    def __init__(self, protocol: str):
        if protocol not in {"jflow", "netstream"}:
            raise ValueError("unsupported compatible vendor protocol")
        self.protocol = protocol
        self.netflow = NetFlowParser()
        self.ipfix = IPFIXParser()

    def parse(self, payload: bytes, exporter_ip: str, received_at: datetime | None = None) -> list[NormalizedFlow]:
        if len(payload) < 2:
            raise FlowParseError("flow packet is too short")
        version = _u(payload, 0, 2)
        if version in (5, 9):
            records = self.netflow.parse(payload, exporter_ip, received_at)
        elif version == 10:
            records = self.ipfix.parse(payload, exporter_ip, received_at)
        else:
            raise FlowParseError(f"{self.protocol} requires NetFlow v5/v9 or IPFIX compatibility")
        for record in records:
            record.protocol = self.protocol
            record.raw_fields.setdefault("wire_protocol", "netflow" if version in (5, 9) else "ipfix")
        return records


class JFlowParser(CompatibleVendorFlowParser):
    def __init__(self):
        super().__init__("jflow")


class NetStreamParser(CompatibleVendorFlowParser):
    def __init__(self):
        super().__init__("netstream")
