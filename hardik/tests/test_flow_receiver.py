import asyncio
import struct
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from backend.flow.receiver import FlowReceiver
import backend.main as main


def v5_packet() -> bytes:
    header = struct.pack("!HHIIIIBBH", 5, 1, 1, 100_000, 1_700_000_000, 0, 0, 0, 0)
    record = bytearray(48)
    record[0:4] = bytes((10, 0, 0, 1))
    record[4:8] = bytes((10, 0, 0, 2))
    record[16:20] = (20).to_bytes(4, "big")
    record[20:24] = (2000).to_bytes(4, "big")
    record[24:28] = (99_000).to_bytes(4, "big")
    record[28:32] = (99_500).to_bytes(4, "big")
    record[32:34] = (1234).to_bytes(2, "big")
    record[34:36] = (443).to_bytes(2, "big")
    record[38] = 6
    return header + bytes(record)


def ipfix_packet() -> bytes:
    template = struct.pack("!HH", 256, 8) + b"".join(struct.pack("!HH", field, size) for field, size in (
        (8, 4), (12, 4), (7, 2), (11, 2), (4, 1), (1, 4), (2, 4), (10, 2)
    ))
    template_set = struct.pack("!HH", 2, len(template) + 4) + template
    values = bytes((203, 0, 113, 1)) + bytes((203, 0, 113, 2)) + struct.pack("!HHBIIH", 1111, 22, 6, 123, 4, 1)
    data_set = struct.pack("!HH", 256, len(values) + 4) + values
    body = template_set + data_set
    return struct.pack("!HHIII", 10, len(body) + 16, 1_700_000_000, 0, 77) + body


def v9_packet() -> bytes:
    template = struct.pack("!HH", 256, 10) + b"".join(struct.pack("!HH", field, size) for field, size in (
        (8, 4), (12, 4), (7, 2), (11, 2), (4, 1), (1, 4), (2, 4), (10, 2), (14, 2), (22, 4)
    ))
    template_set = struct.pack("!HH", 0, len(template) + 4) + template
    values = bytes((192, 0, 2, 1)) + bytes((198, 51, 100, 2)) + struct.pack("!HHBIIHHI", 1000, 80, 17, 900, 9, 2, 3, 99_900)
    data_set = struct.pack("!HH", 256, len(values) + 4) + values
    return struct.pack("!HHIIII", 9, 2, 0, 99_000, 1_700_000_000, 7) + template_set + data_set


def sflow_packet() -> bytes:
    ethernet = bytes.fromhex("00112233445566778899aabb0800")
    ipv4 = bytes.fromhex("4500001c0000000040110000c0000201c6336402")
    udp = struct.pack("!HHHH", 5555, 2055, 8, 0)
    frame = ethernet + ipv4 + udp
    packet_header = struct.pack("!IIII", 1, len(frame), 0, len(frame)) + frame
    flow_record = struct.pack("!II", 1, len(packet_header)) + packet_header
    sample = struct.pack("!IIIIIIII", 9, 4, 100, 1000, 0, 7, 8, 1) + flow_record
    return struct.pack("!II", 5, 1) + bytes((192, 0, 2, 10)) + struct.pack("!IIII", 1, 2, 3000, 1) + struct.pack("!II", 1, len(sample)) + sample


class _Ingest:
    def __init__(self, maxsize=10):
        self.queue = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def submit_nowait(self, flow):
        try:
            self.queue.put_nowait(flow)
            return True
        except asyncio.QueueFull:
            self.dropped += 1
            return False


@pytest.mark.parametrize(
    ("listener", "payload", "protocol"),
    [("netflow", v5_packet(), "netflow"), ("netflow", ipfix_packet(), "ipfix"), ("sflow", sflow_packet(), "sflow")],
)
def test_receiver_dispatches_protocols(listener, payload, protocol):
    ingest = _Ingest()
    receiver = FlowReceiver(ingest)
    receiver.handle_datagram(listener, payload, "192.0.2.10")
    record = ingest.queue.get_nowait()
    assert record.protocol == protocol
    assert record.exporter_ip == "192.0.2.10"
    assert receiver.stats.received_datagrams == 1
    assert receiver.stats.parsed_records == 1


def test_receiver_dispatches_netflow_v9():
    ingest = _Ingest()
    receiver = FlowReceiver(ingest)
    receiver.handle_datagram("netflow", v9_packet(), "192.0.2.10")
    assert receiver.stats.received_datagrams == 1
    assert receiver.stats.parsed_records == 1
    assert ingest.queue.get_nowait().source_version == "9"


def test_receiver_drops_malformed_datagram_without_crashing():
    ingest = _Ingest()
    receiver = FlowReceiver(ingest)
    receiver.handle_datagram("netflow", b"\x00", "192.0.2.10")
    assert receiver.stats.malformed_datagrams == 1
    assert ingest.queue.empty()


def test_receiver_drops_unsupported_version_without_crashing():
    ingest = _Ingest()
    receiver = FlowReceiver(ingest)
    receiver.handle_datagram("netflow", b"\x00\x04", "192.0.2.10")
    assert receiver.stats.unsupported_datagrams == 1
    assert ingest.queue.empty()


def test_receiver_handles_queue_full():
    ingest = _Ingest(maxsize=1)
    ingest.queue.put_nowait(object())
    receiver = FlowReceiver(ingest)
    receiver.handle_datagram("netflow", v5_packet(), "192.0.2.10")
    assert receiver.stats.dropped_records == 1
    assert ingest.dropped == 1


def test_receiver_start_stop_binds_two_configured_listeners():
    ingest = _Ingest()
    receiver = FlowReceiver(ingest, bind_host="127.0.0.1", netflow_port=0, sflow_port=0)
    transports = [SimpleNamespace(close=lambda: None), SimpleNamespace(close=lambda: None)]

    async def fake_create_datagram_endpoint(factory, local_addr):
        protocol = factory()
        transport = transports.pop(0)
        protocol.connection_made(transport)
        return transport, protocol

    async def scenario():
        loop = asyncio.get_running_loop()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(loop, "create_datagram_endpoint", fake_create_datagram_endpoint)
        await receiver.start()
        assert receiver._started is True
        assert len(receiver._transports) == 2
        await receiver.stop()
        monkeypatch.undo()

    asyncio.run(scenario())
    assert receiver._started is False
    assert receiver._transports == []


def test_flow_disabled_default_is_safe():
    from backend.config.settings import Settings

    assert Settings().flow_enabled is False


def test_lifespan_starts_writer_before_receiver_and_stops_both(monkeypatch):
    events: list[str] = []

    class FakeFlowIngestService:
        def __init__(self, _factory):
            self.persisted = 0

        async def start(self):
            events.append("ingest_start")

        async def stop(self):
            events.append("ingest_stop")

    class FakeFlowReceiver:
        def __init__(self, ingest, bind_host, netflow_port, sflow_port):
            self.ingest = ingest
            self.bind_host = bind_host
            self.netflow_port = netflow_port
            self.sflow_port = sflow_port

        async def start(self):
            events.append("receiver_start")

        async def stop(self):
            events.append("receiver_stop")

    class FakeLease:
        def acquire(self):
            events.append("lease_acquire")
            return False

        def release(self):
            events.append("lease_release")

    class FakeLinuxScheduler:
        async def restore_enabled_servers(self):
            events.append("linux_restore")

        async def shutdown(self):
            events.append("linux_shutdown")

    @contextmanager
    def fake_session():
        yield SimpleNamespace()

    monkeypatch.setattr(main, "FlowIngestService", FakeFlowIngestService)
    monkeypatch.setattr(main, "FlowReceiver", FakeFlowReceiver)
    monkeypatch.setattr(main, "SchedulerLease", FakeLease)
    monkeypatch.setattr(main, "LinuxMonitoringScheduler", FakeLinuxScheduler)
    monkeypatch.setattr(main, "SessionLocal", fake_session)
    monkeypatch.setattr(main, "get_polling_scheduler", lambda: asyncio.sleep(0, result=None))
    monkeypatch.setattr(main, "shutdown_polling_scheduler", lambda: asyncio.sleep(0))
    monkeypatch.setattr(main, "run_migrations", lambda _engine: events.append("migrations"))
    monkeypatch.setattr(main.Base.metadata, "create_all", lambda *args, **kwargs: events.append("create_all"))
    monkeypatch.setattr(main, "seed_rbac", lambda _db: events.append("seed_rbac"))
    monkeypatch.setattr(main, "seed_ouis_and_products", lambda _db: events.append("seed_ouis"))
    monkeypatch.setattr(main.settings, "flow_enabled", True)
    monkeypatch.setattr(main.settings, "flow_bind_host", "127.0.0.1")
    monkeypatch.setattr(main.settings, "flow_netflow_port", 2055)
    monkeypatch.setattr(main.settings, "flow_sflow_port", 6343)

    app = SimpleNamespace(state=SimpleNamespace())

    async def scenario():
        async with main.lifespan(app):
            assert isinstance(app.state.flow_ingest, FakeFlowIngestService)
            assert isinstance(app.state.flow_receiver, FakeFlowReceiver)
            assert events[:4] == ["create_all", "migrations", "seed_rbac", "seed_ouis"]
            assert "ingest_start" in events
            assert "receiver_start" in events
            assert events.index("ingest_start") < events.index("receiver_start")
        assert events[-4:] == ["receiver_stop", "ingest_stop", "linux_shutdown", "lease_release"]

    asyncio.run(scenario())


def test_lifespan_skips_flow_when_disabled(monkeypatch):
    class FakeFlowIngestService:
        def __init__(self, _factory):
            raise AssertionError("flow ingest should not be created")

    class FakeFlowReceiver:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("flow receiver should not be created")

    @contextmanager
    def fake_session():
        yield SimpleNamespace()

    monkeypatch.setattr(main, "FlowIngestService", FakeFlowIngestService)
    monkeypatch.setattr(main, "FlowReceiver", FakeFlowReceiver)
    monkeypatch.setattr(main.settings, "flow_enabled", False)
    monkeypatch.setattr(main, "SchedulerLease", lambda: SimpleNamespace(acquire=lambda: False, release=lambda: None))
    monkeypatch.setattr(main, "LinuxMonitoringScheduler", lambda: SimpleNamespace(restore_enabled_servers=lambda: asyncio.sleep(0), shutdown=lambda: asyncio.sleep(0)))
    monkeypatch.setattr(main, "SessionLocal", fake_session)
    monkeypatch.setattr(main.Base.metadata, "create_all", lambda **_: None)
    monkeypatch.setattr(main, "run_migrations", lambda _engine: None)
    monkeypatch.setattr(main, "seed_rbac", lambda _db: None)
    monkeypatch.setattr(main, "seed_ouis_and_products", lambda _db: None)
    monkeypatch.setattr(main, "get_polling_scheduler", lambda: asyncio.sleep(0, result=None))
    monkeypatch.setattr(main, "shutdown_polling_scheduler", lambda: asyncio.sleep(0))

    app = SimpleNamespace(state=SimpleNamespace())

    async def scenario():
        async with main.lifespan(app):
            assert app.state.flow_ingest is None
            assert app.state.flow_receiver is None

    asyncio.run(scenario())
