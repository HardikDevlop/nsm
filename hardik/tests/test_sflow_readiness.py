import struct
from datetime import datetime

import pytest

from backend.flow.correlation import FlowCorrelationResolver
from backend.flow.parsers import FlowParseError, SFlowCounterSample, SFlowParser
from backend.flow.service import counter_values


def _datagram(sample: bytes, *, agent: bytes = bytes((192, 0, 2, 10)), address_type: int = 1,
              sub_agent: int = 2, sequence: int = 1, uptime: int = 3000) -> bytes:
    return (
        struct.pack("!II", 5, address_type) + agent +
        struct.pack("!IIII", sub_agent, sequence, uptime, 1) +
        struct.pack("!II", 1, len(sample)) + sample
    )


def _flow_sample(frame: bytes, *, input_if: int = 15, output_if: int = 16,
                 sample_pool: int = 1000, drops: int = 3, sequence: int = 9,
                 extra_records: bytes = b"") -> bytes:
    packet_header = struct.pack("!IIII", 1, len(frame), 0, len(frame)) + frame
    packet_record = struct.pack("!II", 1, len(packet_header)) + packet_header
    sample = struct.pack("!IIIIIIII", sequence, 4, 100, sample_pool, drops, input_if, output_if, 1)
    return sample + packet_record + extra_records


def _ethernet_ipv4(vlan: int | None = None) -> bytes:
    macs = bytes.fromhex("00112233445566778899aabb")
    tag = struct.pack("!HH", 0x8100, vlan) if vlan is not None else b""
    ethertype = struct.pack("!H", 0x0800)
    ipv4 = bytes.fromhex("4500001c0000000040110000c0000201c6336402")
    udp = struct.pack("!HHHH", 5555, 2055, 8, 0)
    return macs + tag + ethertype + ipv4 + udp


def _ethernet_ipv6() -> bytes:
    macs = bytes.fromhex("aabbccddeeff102030405060")
    ipv6 = bytes.fromhex(
        "60000000000c1140" +
        "20010db8000000000000000000000001" +
        "20010db8000000000000000000000002"
    )
    return macs + struct.pack("!H", 0x86DD) + ipv6 + struct.pack("!HHHH", 6000, 6001, 12, 0)


def _counter_datagram(*, if_index: int = 15) -> bytes:
    values = (if_index, 6, 1_000_000_000, 1, 3, 100, 10, 20, 30, 4, 5,
              200, 11, 21, 31, 6, 7)
    record = struct.pack("!IIQIIQIIIIIQIIIIII", *values, 0)
    sample = struct.pack("!III", 44, 4, 1) + struct.pack("!II", 1, len(record)) + record
    payload = struct.pack("!II", 5, 1) + bytes((192, 0, 2, 10)) + struct.pack("!IIII", 2, 8, 4000, 1)
    return payload + struct.pack("!II", 2, len(sample)) + sample


def test_ipv4_agent_and_packet_header_metadata_are_retained():
    flow = SFlowParser().parse(_datagram(_flow_sample(_ethernet_ipv4())), "192.0.2.10")[0]
    metadata = flow.raw_fields["sflow"]
    assert metadata["agent_address"] == "192.0.2.10"
    assert metadata["sub_agent_id"] == 2
    assert metadata["datagram_sequence"] == 1
    assert metadata["agent_uptime"] == 3000
    assert metadata["sample_count"] == 1
    assert metadata["sample_pool"] == 1000
    assert metadata["drops"] == 3
    assert metadata["sampled_packet_length"] == len(_ethernet_ipv4())
    assert metadata["source_mac"] == "66:77:88:99:aa:bb"
    assert metadata["destination_mac"] == "00:11:22:33:44:55"
    assert (flow.input_interface_id, flow.output_interface_id) == (15, 16)
    assert flow.raw_fields["quality"] == "packet_sample"


def test_ipv6_agent_and_sample_are_supported():
    agent = bytes.fromhex("20010db800000000000000000000000a")
    flow = SFlowParser().parse(_datagram(_flow_sample(_ethernet_ipv6()), agent=agent, address_type=2), "2001:db8::a")[0]
    assert flow.raw_fields["sflow"]["agent_address"] == "2001:db8::a"
    assert (flow.src_ip, flow.dst_ip) == ("2001:db8::1", "2001:db8::2")
    assert (flow.src_port, flow.dst_port, flow.ip_protocol) == (6000, 6001, 17)


def test_vlan_is_stored_only_when_exported():
    vlan_flow = SFlowParser().parse(_datagram(_flow_sample(_ethernet_ipv4(123))), "192.0.2.10")[0]
    plain_flow = SFlowParser().parse(_datagram(_flow_sample(_ethernet_ipv4())), "192.0.2.10")[0]
    assert vlan_flow.raw_fields["sflow"]["vlan_id"] == 123
    assert plain_flow.raw_fields["sflow"]["vlan_id"] is None


def test_sequence_gap_restart_and_wrap_are_distinguished():
    parser = SFlowParser()
    packet = _datagram(_flow_sample(_ethernet_ipv4()), sequence=10, uptime=100)
    assert parser.parse(packet, "192.0.2.10")[0].raw_fields["sflow"]["sequence"]["status"] == "initial"
    assert parser.parse(_datagram(_flow_sample(_ethernet_ipv4()), sequence=12, uptime=200), "192.0.2.10")[0].raw_fields["sflow"]["sequence"] == {"status": "gap", "gap": True, "lost": 1}
    assert parser.parse(_datagram(_flow_sample(_ethernet_ipv4()), sequence=13, uptime=50), "192.0.2.10")[0].raw_fields["sflow"]["sequence"]["status"] == "restart"
    parser = SFlowParser()
    parser.parse(_datagram(_flow_sample(_ethernet_ipv4()), sequence=0xFFFFFFFF, uptime=100), "192.0.2.10")
    assert parser.parse(_datagram(_flow_sample(_ethernet_ipv4()), sequence=0, uptime=200), "192.0.2.10")[0].raw_fields["sflow"]["sequence"]["status"] == "wrap"


def test_generic_interface_counter_sample_is_separate_and_correlatable():
    result = SFlowParser().parse_datagram(_counter_datagram(), "192.0.2.10")
    assert result.flows == []
    assert len(result.counters) == 1
    counter = result.counters[0]
    assert isinstance(counter, SFlowCounterSample)
    assert (counter.if_index, counter.if_speed, counter.if_in_octets, counter.if_out_octets) == (15, 1_000_000_000, 100, 200)
    assert counter.raw_fields["quality"] == "counter_sample"
    assert "protocol" not in counter_values(counter)

    class Result:
        def mappings(self): return self
        def all(self): return [{"id": 10, "hostname": "Core-switch"}]

    class Db:
        def execute(self, statement, params):
            if "FROM devices" in str(statement): return Result()
            return type("Interfaces", (), {"mappings": lambda self: self, "all": lambda self: [{"if_index": 15, "name": "GigabitEthernet1/0/15"}]})()

    FlowCorrelationResolver().correlate_counters(Db(), [counter])
    assert counter.device_id == 10
    assert counter.interface_name == "GigabitEthernet1/0/15"


def test_unknown_record_and_truncated_datagram_are_safe():
    unknown = struct.pack("!II", 99, 4) + b"\x00\x00\x00\x00"
    unknown_sample = struct.pack("!IIIIIIII", 9, 4, 100, 1000, 0, 7, 8, 1) + unknown
    assert SFlowParser().parse(_datagram(unknown_sample), "192.0.2.10") == []
    with pytest.raises(FlowParseError):
        SFlowParser().parse(_datagram(_flow_sample(_ethernet_ipv4()))[:-1], "192.0.2.10")
