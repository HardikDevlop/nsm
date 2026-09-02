import asyncio
import struct
from datetime import datetime

import pytest

from backend.flow.models import NormalizedFlow
from backend.flow.parsers import FlowParseError, IPFIXParser, NetFlowParser
from backend.flow.service import FlowIngestService


def v5_packet() -> bytes:
    header = struct.pack("!HHIIIIBBH", 5, 1, 1, 100_000, 1_700_000_000, 0, 0, 0, 0)
    record = bytearray(48)
    record[0:4] = bytes((10, 0, 0, 1))
    record[4:8] = bytes((10, 0, 0, 2))
    record[12:14] = (3).to_bytes(2, "big")
    record[14:16] = (4).to_bytes(2, "big")
    record[16:20] = (20).to_bytes(4, "big")
    record[20:24] = (2000).to_bytes(4, "big")
    record[24:28] = (99_000).to_bytes(4, "big")
    record[28:32] = (99_500).to_bytes(4, "big")
    record[32:34] = (1234).to_bytes(2, "big")
    record[34:36] = (443).to_bytes(2, "big")
    record[38] = 6
    return header + bytes(record)


def v9_packet() -> bytes:
    template = struct.pack("!HH", 256, 10) + b"".join(struct.pack("!HH", field, size) for field, size in (
        (8, 4), (12, 4), (7, 2), (11, 2), (4, 1), (1, 4), (2, 4), (10, 2), (14, 2), (22, 4)
    ))
    template_set = struct.pack("!HH", 0, len(template) + 4) + template
    values = bytes((192, 0, 2, 1)) + bytes((198, 51, 100, 2)) + struct.pack("!HHBIIHHI", 1000, 80, 17, 900, 9, 2, 3, 99_900)
    data_set = struct.pack("!HH", 256, len(values) + 4) + values
    header = struct.pack("!HHIIII", 9, 2, 0, 99_000, 1_700_000_000, 7)
    return header + template_set + data_set


def ipfix_packet() -> bytes:
    template = struct.pack("!HH", 256, 8) + b"".join(struct.pack("!HH", field, size) for field, size in (
        (8, 4), (12, 4), (7, 2), (11, 2), (4, 1), (1, 4), (2, 4), (10, 2)
    ))
    template_set = struct.pack("!HH", 2, len(template) + 4) + template
    values = bytes((203, 0, 113, 1)) + bytes((203, 0, 113, 2)) + struct.pack("!HHBIIH", 1111, 22, 6, 123, 4, 1)
    data_set = struct.pack("!HH", 256, len(values) + 4) + values
    body = template_set + data_set
    return struct.pack("!HHIII", 10, len(body) + 16, 1_700_000_000, 0, 77) + body


def test_netflow_v5_normalizes_core_fields():
    flow = NetFlowParser().parse(v5_packet(), "192.0.2.10")[0]
    assert (flow.protocol, flow.source_version) == ("netflow", "5")
    assert (flow.src_ip, flow.dst_ip, flow.src_port, flow.dst_port) == ("10.0.0.1", "10.0.0.2", 1234, 443)
    assert (flow.bytes, flow.packets, flow.input_interface_id, flow.output_interface_id) == (2000, 20, 3, 4)
    flow.validate()


def test_netflow_v9_template_and_data_are_normalized():
    flow = NetFlowParser().parse(v9_packet(), "192.0.2.11")[0]
    assert flow.source_version == "9"
    assert flow.src_ip == "192.0.2.1" and flow.dst_ip == "198.51.100.2"
    assert (flow.ip_protocol, flow.bytes, flow.packets) == (17, 900, 9)


def test_ipfix_template_and_data_are_normalized():
    flow = IPFIXParser().parse(ipfix_packet(), "192.0.2.12")[0]
    assert (flow.protocol, flow.source_version, flow.observation_domain) == ("ipfix", "10", "77")
    assert (flow.src_ip, flow.dst_ip, flow.bytes, flow.packets) == ("203.0.113.1", "203.0.113.2", 123, 4)


def test_parser_rejects_truncated_and_unsupported_packets():
    with pytest.raises(FlowParseError):
        NetFlowParser().parse(b"\x00\x05", "192.0.2.1")
    with pytest.raises(FlowParseError, match="unsupported"):
        NetFlowParser().parse(struct.pack("!H", 4) + b"\x00\x00", "192.0.2.1")


class _Db:
    def __init__(self):
        self.rows = []
        self.commits = 0

    def __enter__(self): return self
    def __exit__(self, *_): pass
    def execute(self, _statement, rows): self.rows.extend(rows)
    def commit(self): self.commits += 1


def test_ingestion_queue_batches_and_drops_when_full():
    db = _Db()
    service = FlowIngestService(lambda: db, queue_size=1, batch_size=2, flush_seconds=0.01)
    flow = NormalizedFlow("192.0.2.1", "netflow", datetime(2026, 1, 1), datetime(2026, 1, 1), datetime(2026, 1, 1))

    async def scenario():
        await service.start()
        accepted = [await service.submit(flow) for _ in range(5)]
        await service.stop()
        return accepted

    accepted = asyncio.run(scenario())
    assert any(accepted) and service.dropped > 0
    assert service.persisted == sum(accepted)
    assert db.commits >= 1
