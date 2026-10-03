import asyncio
from types import SimpleNamespace

import pytest

from backend.services.remote_access.terminal_websocket import TerminalWebSocket


class WebSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []
        self.accepted = False
        self.closed = []
    async def accept(self): self.accepted = True
    async def receive(self):
        try: return next(self.messages)
        except StopIteration: return {"type": "websocket.disconnect"}
    async def send_bytes(self, data): self.sent.append(("bytes", data))
    async def send_json(self, data): self.sent.append(("json", data))
    async def close(self, **kwargs): self.closed.append(kwargs)


class Adapter:
    def __init__(self): self.writes = []; self.resizes = []; self.closed = False; self.outputs = [b"Username:", b""]
    def write(self, data): self.writes.append(data)
    def resize(self, cols, rows): self.resizes.append((cols, rows))
    def read(self, *args):
        value = self.outputs.pop(0) if self.outputs else b""
        if value == b"": self.closed = True
        return value
    def is_alive(self): return not self.closed
    def disconnect(self): self.closed = True


class Manager:
    def __init__(self, owner=7):
        self.adapter = Adapter()
        self.record = SimpleNamespace(status="connected", user_id=owner)
        self.managed = SimpleNamespace(record=self.record, adapter=self.adapter)
        self.disconnected = []
        self.touches = 0
    def get_session(self, _): return self.managed if self.record.status == "connected" else None
    def is_alive(self, _): return self.record.status == "connected" and self.adapter.is_alive()
    def touch(self, _): self.touches += 1
    def disconnect_session(self, _, reason="Disconnected"):
        self.disconnected.append(reason); self.record.status = "disconnected"; self.adapter.disconnect()
    def reconcile_transport(self, _, reason="Connection lost"):
        self.disconnected.append(reason); self.record.status = "disconnected"; self.adapter.disconnect()


def test_attachment_input_resize_ping_and_reuses_adapter(monkeypatch):
    manager = Manager()
    service = TerminalWebSocket(manager)
    ws = WebSocket([])
    async def direct(function, *args): return function(*args)
    monkeypatch.setattr("backend.services.remote_access.terminal_websocket.asyncio.to_thread", direct)
    async def exercise():
        await service._handle_message(ws, "sid", manager.adapter, {"text": '{"type":"input","data":"secret-value"}'})
        await service._handle_message(ws, "sid", manager.adapter, {"text": '{"type":"resize","cols":120,"rows":40}'})
        await service._handle_message(ws, "sid", manager.adapter, {"text": '{"type":"ping"}'})
    asyncio.run(exercise())
    assert manager.adapter.writes == ["secret-value"]
    assert manager.adapter.resizes == [(120, 40)]
    assert ("json", {"type": "pong"}) in ws.sent
    assert manager.get_session("sid").adapter is manager.adapter
    assert "secret-value" not in repr(ws.sent)


def test_denies_other_owner_without_accepting():
    manager, ws = Manager(), WebSocket([])
    asyncio.run(TerminalWebSocket(manager).serve(ws, "sid", user_id=99))
    assert not ws.accepted and ws.closed[0]["code"] == 4403


def test_explicit_disconnect_and_remote_disconnect_cleanup(monkeypatch):
    manager = Manager()
    ws = WebSocket([])
    async def direct(function, *args): return function(*args)
    monkeypatch.setattr("backend.services.remote_access.terminal_websocket.asyncio.to_thread", direct)
    asyncio.run(TerminalWebSocket(manager)._handle_message(ws, "sid", manager.adapter, {"text": '{"type":"disconnect"}'}))
    assert manager.disconnected == ["Client requested disconnect"]


def test_adapter_read_failure_is_connection_loss_not_websocket_failure(monkeypatch):
    manager = Manager()
    manager.adapter.outputs = [b"output"]
    manager.adapter.read = lambda *args: (_ for _ in ()).throw(ConnectionError("secret output"))
    service = TerminalWebSocket(manager)
    ws = WebSocket([])
    async def direct(function, *args): return function(*args)
    monkeypatch.setattr("backend.services.remote_access.terminal_websocket.asyncio.to_thread", direct)
    asyncio.run(service._forward_output(ws, "sid", manager.adapter))
    assert manager.disconnected == ["Connection lost"]
    assert "secret output" not in repr(manager.disconnected)


def test_websocket_send_failure_is_recorded_once(monkeypatch):
    manager = Manager()
    class BrokenWebSocket(WebSocket):
        async def send_bytes(self, data): raise RuntimeError("socket details")
    ws = BrokenWebSocket([])
    async def direct(function, *args): return function(*args)
    monkeypatch.setattr("backend.services.remote_access.terminal_websocket.asyncio.to_thread", direct)
    asyncio.run(TerminalWebSocket(manager)._forward_output(ws, "sid", manager.adapter))
    assert manager.disconnected == ["WebSocket/transport failure"]
