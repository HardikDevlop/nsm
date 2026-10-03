import socket

import pytest

from backend.services.remote_access.telnet_service import TelnetConnectionAdapter, TelnetConnectionError


class FakeSocket:
    def __init__(self, incoming=b"Username:\r\nPassword:"):
        self.incoming, self.sent, self.closed = incoming, [], False

    def settimeout(self, value): self.timeout = value
    def fileno(self): return -1 if self.closed else 10
    def recv(self, size):
        data, self.incoming = self.incoming[:size], self.incoming[size:]
        return data
    def sendall(self, data): self.sent.append(bytes(data))
    def shutdown(self, _): self.closed = True
    def close(self): self.closed = True


def connected(monkeypatch, fake=None, port=23):
    fake = fake or FakeSocket()
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout: (assert_address(address, port), fake)[1])
    return TelnetConnectionAdapter("router", port=port, username="u", password="secret").connect(), fake


def assert_address(address, port):
    assert address == ("router", port)


def test_default_and_custom_port(monkeypatch):
    adapter, _ = connected(monkeypatch)
    assert adapter.port == 23
    adapter.disconnect()
    adapter, _ = connected(monkeypatch, port=2323)
    assert adapter.port == 2323


def test_raw_prompt_read_and_multiple_writes(monkeypatch):
    adapter, fake = connected(monkeypatch)
    monkeypatch.setattr("backend.services.remote_access.telnet_service.select.select", lambda *args: ([fake], [], []))
    assert adapter.read() == b"Username:\r\nPassword:"
    adapter.write("first\r")
    adapter.write(b"second\r")
    assert fake.sent == [b"first\r", b"second\r"]


def test_telnet_negotiation_is_refused_without_leaking_credentials(monkeypatch):
    fake = FakeSocket(b"\xff\xfb\x01Username:")
    adapter, fake = connected(monkeypatch, fake)
    monkeypatch.setattr("backend.services.remote_access.telnet_service.select.select", lambda *args: ([fake], [], []))
    assert adapter.read() == b"Username:"
    assert fake.sent == [bytes((255, 254, 1))]
    assert "secret" not in repr(fake.sent)


@pytest.mark.parametrize("error", [socket.timeout(), ConnectionRefusedError(), ConnectionResetError()])
def test_connect_failures_cleanup(monkeypatch, error):
    fake = FakeSocket()
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(socket, "create_connection", fail)
    adapter = TelnetConnectionAdapter("router", password="secret")
    with pytest.raises(TelnetConnectionError): adapter.connect()
    assert adapter._socket is None and not adapter.is_alive()


def test_timeout_remote_close_alive_and_idempotent_disconnect(monkeypatch):
    adapter, fake = connected(monkeypatch, FakeSocket(b""))
    monkeypatch.setattr("backend.services.remote_access.telnet_service.select.select", lambda *args: ([], [], []))
    assert adapter.read(timeout=0.01) == b""
    assert adapter.is_alive()
    monkeypatch.setattr("backend.services.remote_access.telnet_service.select.select", lambda *args: ([fake], [], []))
    assert adapter.read() == b""
    assert not adapter.is_alive()
    adapter.disconnect()
    adapter.disconnect()


def test_metadata_marks_telnet_unencrypted():
    assert TelnetConnectionAdapter("router").metadata["encrypted"] is False
    assert TelnetConnectionAdapter("router").metadata["security"] == "insecure_unencrypted"
