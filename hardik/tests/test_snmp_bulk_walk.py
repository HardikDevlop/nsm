import asyncio
from types import SimpleNamespace

import pytest
from pysnmp.proto.rfc1902 import OctetString
from backend.snmp import client as transport
from backend.snmp.credentials import SNMPCredentials


@pytest.fixture
def harness(monkeypatch):
    import pysnmp.hlapi.asyncio as hlapi
    closed = []
    monkeypatch.setattr(hlapi, 'SnmpEngine', lambda: SimpleNamespace(transportDispatcher=SimpleNamespace(closeDispatcher=lambda: closed.append(True))))
    monkeypatch.setattr(hlapi, 'UdpTransportTarget', lambda *a, **kw: None)
    monkeypatch.setattr(transport, '_run_in_thread', lambda coro, timeout: asyncio.run(coro))
    client = transport.SNMPClient(SNMPCredentials())
    monkeypatch.setattr(client, '_make_auth', lambda: None)
    return client, hlapi, closed


def test_bulk_walk_collects_65_rows_in_three_requests(harness, monkeypatch):
    client, hlapi, closed = harness
    calls = []
    async def bulk(*args, **kwargs):
        start = len(calls) * 25 + 1
        calls.append(args[5])
        rows = [[(f'1.3.6.1.2.1.{i}', OctetString(str(i)))] for i in range(start, min(start + 25, 66))]
        if start == 51:
            rows.append([('1.3.6.1.3.1', OctetString('outside'))])
        return None, 0, 0, rows
    monkeypatch.setattr(hlapi, 'bulkCmd', bulk)
    result = client.walk('192.0.2.1', '1.3.6.1.2.1')
    assert len(result) == 65
    assert len(calls) == 3
    assert closed == [True]


def test_rejected_bulk_falls_back_to_next_and_stops_repeated_oid(harness, monkeypatch):
    client, hlapi, closed = harness
    calls = []
    async def bulk(*args, **kwargs):
        calls.append('bulk')
        return None, 1, 0, []
    async def next_row(*args, **kwargs):
        calls.append('next')
        return None, 0, 0, [[('1.3.6.1.2.1.1', OctetString('row'))]]
    monkeypatch.setattr(hlapi, 'bulkCmd', bulk)
    monkeypatch.setattr(hlapi, 'nextCmd', next_row)
    assert client.walk('192.0.2.1', '1.3.6.1.2.1') == {'1.3.6.1.2.1.1': 'row'}
    assert calls == ['bulk', 'next', 'next']
    assert closed == [True]


def test_dispatcher_closed_on_transport_failure(harness, monkeypatch):
    client, hlapi, closed = harness
    async def bulk(*args, **kwargs):
        raise TimeoutError('device timed out')
    monkeypatch.setattr(hlapi, 'bulkCmd', bulk)
    with pytest.raises(TimeoutError):
        client.walk('192.0.2.1', '1.3.6.1.2.1')
    assert closed == [True]
