import struct
from datetime import datetime, timezone

import pytest

from backend.flow.parsers import FlowParseError, IPFIXParser


def _template_set(template_id: int, fields: list[tuple[int, int]], *, domain: int = 7, exporter: str = "192.0.2.10") -> bytes:
    body = struct.pack("!HH", template_id, len(fields))
    for element_id, length in fields:
        body += struct.pack("!HH", element_id, length)
    return _message(struct.pack("!HH", 2, len(body) + 4) + body, domain=domain)


def _message(sets: bytes, *, export_time: int = 1_700_000_000, sequence: int = 1, domain: int = 7) -> bytes:
    return struct.pack("!HHIII", 10, len(sets) + 16, export_time, sequence, domain) + sets


def _data_set(template_id: int, values: bytes, *, export_time: int = 1_700_000_000, sequence: int = 1, domain: int = 7) -> bytes:
    return _message(struct.pack("!HH", template_id, len(values) + 4) + values,
                    export_time=export_time, sequence=sequence, domain=domain)


def _full_flow_values(start_ms: int = 1_700_000_100_000, end_ms: int = 1_700_000_101_000) -> bytes:
    return (
        bytes((203, 0, 113, 1)) + bytes((203, 0, 113, 2)) +
        struct.pack("!HHBIIHHQQ", 1111, 22, 6, 123, 4, 15, 16, start_ms, end_ms)
    )


FLOW_FIELDS = [(8, 4), (12, 4), (7, 2), (11, 2), (4, 1), (1, 4), (2, 4), (10, 2), (14, 2), (152, 8), (153, 8)]


def test_ipfix_header_fields_and_flow_fields_are_decoded_correctly():
    parser = IPFIXParser()
    parser.parse(_template_set(256, FLOW_FIELDS), "192.0.2.10")
    flow = parser.parse(_data_set(256, _full_flow_values(), sequence=44, domain=7), "192.0.2.10")[0]
    assert flow.observation_domain == "7"
    assert flow.src_ip == "203.0.113.1" and flow.dst_ip == "203.0.113.2"
    assert (flow.src_port, flow.dst_port, flow.ip_protocol) == (1111, 22, 6)
    assert (flow.bytes, flow.packets, flow.input_interface_id, flow.output_interface_id) == (123, 4, 15, 16)
    assert flow.flow_start == datetime.fromtimestamp(1_700_000_100, timezone.utc).replace(tzinfo=None)
    assert flow.flow_end == datetime.fromtimestamp(1_700_000_101, timezone.utc).replace(tzinfo=None)
    metadata = flow.raw_fields["ipfix"]
    assert metadata["sequence_number"] == 44
    assert metadata["observation_domain_id"] == 7
    assert metadata["export_time"] == datetime.fromtimestamp(1_700_000_000, timezone.utc).replace(tzinfo=None).isoformat()


def test_template_cache_isolated_by_domain_and_exporter():
    parser = IPFIXParser()
    template = _template_set(256, [(1, 4)], domain=10)
    parser.parse(template, "192.0.2.10")
    assert parser.parse(_data_set(256, struct.pack("!I", 9), domain=11), "192.0.2.10") == []
    assert parser.parse(_data_set(256, struct.pack("!I", 9), domain=10), "192.0.2.11") == []
    assert parser.parse(_data_set(256, struct.pack("!I", 9), domain=10), "192.0.2.10")[0].bytes == 9


def test_ipv6_fields_do_not_overwrite_ipv4_fields():
    parser = IPFIXParser()
    fields = [(27, 16), (28, 16), (1, 4), (2, 4)]
    parser.parse(_template_set(300, fields), "192.0.2.10")
    flow = parser.parse(_data_set(300, bytes.fromhex("20010db8000000000000000000000001" "20010db8000000000000000000000002") + struct.pack("!II", 90, 2)), "192.0.2.10")[0]
    assert (flow.src_ip, flow.dst_ip, flow.bytes, flow.packets) == ("2001:db8::1", "2001:db8::2", 90, 2)


def test_options_template_is_cached_separately_without_creating_flows():
    body = struct.pack("!HHH", 500, 2, 1) + struct.pack("!HH", 149, 4) + struct.pack("!HH", 1, 8)
    parser = IPFIXParser()
    parser.parse(_message(struct.pack("!HH", 3, len(body) + 4) + body), "192.0.2.10")
    assert ("192.0.2.10", 7, 500) in parser.options_templates
    assert parser.parse(_data_set(500, struct.pack("!I", 1)), "192.0.2.10") == []


def test_enterprise_ie_metadata_and_unknown_value_are_preserved():
    parser = IPFIXParser()
    enterprise_id, element_id = 424242, 3000
    body = struct.pack("!HHHHI", 600, 1, 0x8000 | element_id, 4, enterprise_id)
    parser.parse(_message(struct.pack("!HH", 2, len(body) + 4) + body), "192.0.2.10")
    flow = parser.parse(_data_set(600, struct.pack("!I", 0xDEADBEEF)), "192.0.2.10")[0]
    unknown = flow.raw_fields["ipfix"]["unknown_information_elements"][0]
    assert unknown["element_id"] == element_id
    assert unknown["enterprise_id"] == enterprise_id
    assert unknown["value"] == "deadbeef"


def test_refresh_withdrawal_expiration_and_unknown_template_are_safe():
    parser = IPFIXParser(template_ttl_seconds=0.0)
    parser.parse(_template_set(256, [(1, 4)]), "192.0.2.10")
    assert parser.parse(_data_set(256, struct.pack("!I", 1)), "192.0.2.10") == []
    parser = IPFIXParser()
    parser.parse(_template_set(256, [(1, 4)]), "192.0.2.10")
    parser.parse(_template_set(256, [(1, 8)]), "192.0.2.10")
    assert parser.parse(_data_set(256, struct.pack("!Q", 9)), "192.0.2.10")[0].bytes == 9
    withdrawal = _message(struct.pack("!HHHH", 2, 8, 256, 0))
    parser.parse(withdrawal, "192.0.2.10")
    assert parser.parse(_data_set(256, struct.pack("!Q", 9)), "192.0.2.10") == []
    assert parser.diagnostics["unknown_template"] >= 1


def test_sequence_tracking_respects_data_record_count_reset_and_wrap():
    parser = IPFIXParser()
    parser.parse(_template_set(256, [(1, 4)]), "192.0.2.10")
    first = parser.parse(_data_set(256, struct.pack("!I", 1), export_time=1_700_000_000, sequence=100), "192.0.2.10")[0]
    gap = parser.parse(_data_set(256, struct.pack("!I", 2), export_time=1_700_000_001, sequence=102), "192.0.2.10")[0]
    reset = parser.parse(_data_set(256, struct.pack("!I", 3), export_time=1_699_999_990, sequence=1), "192.0.2.10")[0]
    assert first.raw_fields["ipfix"]["sequence"]["status"] == "initial"
    assert gap.raw_fields["ipfix"]["sequence"]["status"] == "gap"
    assert reset.raw_fields["ipfix"]["sequence"]["status"] == "restart"
    parser = IPFIXParser()
    parser.parse(_template_set(256, [(1, 4)]), "192.0.2.10")
    parser.parse(_data_set(256, struct.pack("!I", 1), sequence=0xFFFFFFFF), "192.0.2.10")
    wrapped = parser.parse(_data_set(256, struct.pack("!I", 1), sequence=0), "192.0.2.10")[0]
    assert wrapped.raw_fields["ipfix"]["sequence"]["status"] == "wrap"


def test_malformed_header_and_template_raise_parse_error():
    parser = IPFIXParser()
    with pytest.raises(FlowParseError):
        parser.parse(b"\x00\x0a\x00", "192.0.2.10")
    malformed_template = _message(struct.pack("!HH", 2, 8) + struct.pack("!HH", 256, 2) + struct.pack("!HH", 1, 4))
    with pytest.raises(FlowParseError):
        parser.parse(malformed_template, "192.0.2.10")
