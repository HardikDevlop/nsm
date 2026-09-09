import asyncio

from backend.snmp.client import SNMPClient
from backend.snmp.credentials import SNMPCredentials


def test_configured_snmp_port_is_used_for_get(monkeypatch):
    import pysnmp.hlapi.asyncio as hlapi
    import backend.snmp.client as client_module

    captured = {}

    class Target:
        def __init__(self, address, **_kwargs):
            captured["address"] = address

    async def fake_get_cmd(*_args):
        return None, 0, 0, []

    monkeypatch.setattr(hlapi, "UdpTransportTarget", Target)
    monkeypatch.setattr(hlapi, "getCmd", fake_get_cmd)
    monkeypatch.setattr(client_module, "_run_in_thread", lambda coro, _timeout: asyncio.run(coro))

    result = SNMPClient(SNMPCredentials(port=1161)).get("192.0.2.10", ("1.3.6.1.2.1.1.1.0",))
    assert result == {}
    assert captured["address"] == ("192.0.2.10", 1161)


def test_snmp_port_defaults_to_161():
    assert SNMPCredentials().port == 161
