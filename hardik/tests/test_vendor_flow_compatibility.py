import struct

import pytest

from backend.flow.parsers import FlowParseError, JFlowParser, NetStreamParser


def compatible_v5() -> bytes:
    header = struct.pack("!HHIIIIBBH", 5, 1, 1, 100_000, 1_700_000_000, 0, 0, 0, 0)
    record = bytearray(48)
    record[0:4] = bytes((10, 0, 0, 1))
    record[4:8] = bytes((10, 0, 0, 2))
    record[16:20] = (3).to_bytes(4, "big")
    record[20:24] = (300).to_bytes(4, "big")
    record[32:34] = (1000).to_bytes(2, "big")
    record[34:36] = (443).to_bytes(2, "big")
    record[38] = 6
    return header + bytes(record)


@pytest.mark.parametrize("parser, protocol", [(JFlowParser(), "jflow"), (NetStreamParser(), "netstream")])
def test_wire_compatible_vendor_flow_reuses_common_normalization(parser, protocol):
    flow = parser.parse(compatible_v5(), "192.0.2.20")[0]
    assert flow.protocol == protocol
    assert (flow.src_ip, flow.dst_ip, flow.src_port, flow.dst_port) == ("10.0.0.1", "10.0.0.2", 1000, 443)
    assert flow.raw_fields["wire_protocol"] == "netflow"
    flow.validate()


@pytest.mark.parametrize("parser", [JFlowParser(), NetStreamParser()])
def test_vendor_parser_rejects_non_compatible_wire_format(parser):
    with pytest.raises(FlowParseError, match="compatibility"):
        parser.parse(struct.pack("!H", 42) + b"\x00" * 20, "192.0.2.20")
