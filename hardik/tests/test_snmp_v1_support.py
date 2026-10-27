import asyncio
from types import SimpleNamespace

import pytest
from pysnmp.proto.rfc1902 import OctetString

from backend.snmp import client as transport
from backend.snmp.credentials import SNMPCredentials


def test_versions_normalize_and_validate():
    assert SNMPCredentials(version="1").version == "v1"
    assert SNMPCredentials(version="SNMPv1").version == "v1"
    assert SNMPCredentials(version="v2c").version == "v2c"
    assert SNMPCredentials(version="3", username="u").version == "v3"
    with pytest.raises(ValueError, match="v1, v2c or v3"):
        SNMPCredentials(version="v4")


def test_community_auth_selects_protocol_model(monkeypatch):
    import pysnmp.hlapi.asyncio as hlapi

    calls = []

    def community(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace()

    monkeypatch.setattr(hlapi, "CommunityData", community)
    transport.SNMPClient(SNMPCredentials(version="v1"))._make_auth()
    transport.SNMPClient(SNMPCredentials(version="v2c"))._make_auth()
    assert calls[0][1]["mpModel"] == 0
    assert calls[1][1]["mpModel"] == 1


def test_v1_walk_uses_getnext_and_never_getbulk(monkeypatch):
    import pysnmp.hlapi.asyncio as hlapi

    closed = []
    calls = []
    monkeypatch.setattr(
        hlapi,
        "SnmpEngine",
        lambda: SimpleNamespace(
            transportDispatcher=SimpleNamespace(closeDispatcher=lambda: closed.append(True))
        ),
    )
    monkeypatch.setattr(hlapi, "UdpTransportTarget", lambda *a, **kw: None)
    monkeypatch.setattr(transport, "_run_in_thread", lambda coro, timeout: asyncio.run(coro))

    async def bulk(*args, **kwargs):
        calls.append("bulk")
        return None, 0, 0, []

    async def next_cmd(*args, **kwargs):
        calls.append("next")
        if calls.count("next") == 1:
            return None, 0, 0, [[("1.3.6.1.2.1.1", OctetString("row"))]]
        return None, 0, 0, [[("1.3.6.1.3.1", OctetString("outside"))]]

    monkeypatch.setattr(hlapi, "bulkCmd", bulk)
    monkeypatch.setattr(hlapi, "nextCmd", next_cmd)

    client = transport.SNMPClient(SNMPCredentials(version="v1"))
    assert client.walk("192.0.2.11", "1.3.6.1.2.1") == {
        "1.3.6.1.2.1.1": "row"
    }
    assert calls == ["next", "next"]
    assert closed == [True]

