import struct
from datetime import datetime

import pytest

from backend.flow.models import NormalizedFlow
from backend.flow.parsers import FlowParseError, SFlowParser


def sflow_packet(ether_type="0800") -> bytes:
    # Ethernet + IPv4 + UDP sampled packet header.
    ethernet = bytes.fromhex("00112233445566778899aabb" + ether_type)
    ipv4 = bytes.fromhex("4500001c0000000040110000c0000201c6336402")
    udp = struct.pack("!HHHH", 5555, 2055, 8, 0)
    frame = ethernet + ipv4 + udp
    packet_header = struct.pack("!IIII", 1, len(frame), 0, len(frame)) + frame
    flow_record = struct.pack("!II", 1, len(packet_header)) + packet_header
    sample = struct.pack("!IIIIIIII", 9, 4, 100, 1000, 0, 7, 8, 1) + flow_record
    address = bytes((192, 0, 2, 10))
    header = struct.pack("!II", 5, 1) + address + struct.pack("!IIII", 1, 2, 3000, 1)
    return header + struct.pack("!II", 1, len(sample)) + sample


def test_sflow_normalizes_sampled_ipv4_flow():
    flow = SFlowParser().parse(sflow_packet(), "192.0.2.10")[0]
    assert flow.protocol == "sflow"
    assert (flow.src_ip, flow.dst_ip) == ("192.0.2.1", "198.51.100.2")
    assert (flow.src_port, flow.dst_port, flow.ip_protocol) == (5555, 2055, 17)
    assert (flow.bytes, flow.packets, flow.input_interface_id, flow.output_interface_id) == (len(bytes.fromhex("00112233445566778899aabb0800")) + 28, 1, 7, 8)
    flow.validate()


@pytest.mark.parametrize("payload", [b"", b"\x00\x00\x00\x05", sflow_packet()[:-3]])
def test_sflow_rejects_malformed_datagrams(payload):
    with pytest.raises(FlowParseError):
        SFlowParser().parse(payload, "192.0.2.10")


def test_sflow_no_ip_packet_is_safe_and_returns_no_records():
    assert SFlowParser().parse(sflow_packet("0806"), "192.0.2.10") == []
