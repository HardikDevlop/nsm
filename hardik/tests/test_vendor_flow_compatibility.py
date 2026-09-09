import pytest

from backend.flow.receiver import FlowReceiver


def test_removed_vendor_listener_is_rejected():
    receiver = FlowReceiver(type("Ingest", (), {"submit_nowait": lambda *_: True})())
    with pytest.raises(ValueError, match="unsupported flow listener"):
        receiver._select_parser("netflow", b"\x00\x05")
