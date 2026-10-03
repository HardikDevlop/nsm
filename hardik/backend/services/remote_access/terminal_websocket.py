"""WebSocket bridge for an already-created Remote Access session."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class TerminalWebSocket:
    """Attach a browser to one existing adapter without opening another one."""

    def __init__(self, session_manager):
        self.session_manager = session_manager

    async def serve(self, websocket: WebSocket, session_uuid: str, *, user_id: int, subprotocol: str | None = None) -> None:
        managed = self.session_manager.get_session(session_uuid)
        if managed is None or managed.record.status != "connected":
            await websocket.close(code=4404, reason="Session is not available")
            return
        if managed.record.user_id != user_id:
            await websocket.close(code=4403, reason="Session access denied")
            return

        await websocket.accept(subprotocol=subprotocol)
        if managed.output_history:
            try:
                await websocket.send_bytes(bytes(managed.output_history))
            except Exception:
                self.session_manager.reconcile_transport(session_uuid, reason="WebSocket/transport failure")
                return
        reader = asyncio.create_task(self._forward_output(websocket, session_uuid, managed.adapter))
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                await self._handle_message(websocket, session_uuid, managed.adapter, message)
        except Exception:
            # Do not log exception text: adapter errors may contain device output.
            logger.info("remote_terminal_closed", extra={"session_uuid": session_uuid})
            self.session_manager.reconcile_transport(
                session_uuid, reason="WebSocket/transport failure"
            )
        finally:
            reader.cancel()
            try:
                await reader
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            # A browser attachment is not the remote device session.  Navigation,
            # refresh, and another browser must not terminate the device channel.
            # Transport health is checked by the output/heartbeat loop instead.

    async def _handle_message(self, websocket: WebSocket, session_uuid: str, adapter: Any, message: dict[str, Any]) -> None:
        if "bytes" in message and message["bytes"] is not None:
            try:
                await asyncio.to_thread(adapter.write, message["bytes"])
            except Exception:
                self.session_manager.reconcile_transport(session_uuid, reason="Connection lost")
                return
            self.session_manager.touch(session_uuid)
            return
        raw = message.get("text")
        if raw is None:
            return
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            payload = {"type": "input", "data": raw}
        kind = payload.get("type")
        if kind == "input":
            # Never log payload data: it may be a password entered at a device prompt.
            try:
                await asyncio.to_thread(adapter.write, payload.get("data", ""))
            except Exception:
                self.session_manager.reconcile_transport(session_uuid, reason="Connection lost")
                return
            self.session_manager.touch(session_uuid)
        elif kind == "resize":
            cols, rows = payload.get("cols"), payload.get("rows")
            if not isinstance(cols, int) or not isinstance(rows, int) or cols <= 0 or rows <= 0:
                await websocket.send_json({"type": "error", "code": "INVALID_RESIZE", "message": "Invalid terminal size"})
            elif hasattr(adapter, "resize"):
                await asyncio.to_thread(adapter.resize, cols, rows)
                self.session_manager.touch(session_uuid)
            else:
                await websocket.send_json({"type": "resize_ack", "supported": False})
        elif kind == "ping":
            await websocket.send_json({"type": "pong"})
            self.session_manager.touch(session_uuid)
        elif kind == "disconnect":
            self.session_manager.disconnect_session(session_uuid, reason="Client requested disconnect")
            await websocket.close(code=1000, reason="Disconnected")
        else:
            await websocket.send_json({"type": "error", "code": "INVALID_MESSAGE", "message": "Unsupported terminal message"})

    async def _forward_output(self, websocket: WebSocket, session_uuid: str, adapter: Any) -> None:
        try:
            while self.session_manager.is_alive(session_uuid):
                try:
                    data = await asyncio.to_thread(adapter.read, 65536, 0.1)
                except Exception:
                    # The adapter owns the device-side transport. Do not call
                    # this a WebSocket failure when the remote read failed.
                    self.session_manager.reconcile_transport(
                        session_uuid, reason="Connection lost"
                    )
                    return
                if data:
                    managed = self.session_manager.get_session(session_uuid)
                    if managed is not None:
                        managed.output_history.extend(data)
                        del managed.output_history[:-262144]
                    try:
                        await websocket.send_bytes(data)
                    except Exception:
                        self.session_manager.reconcile_transport(
                            session_uuid, reason="WebSocket/transport failure"
                        )
                        return
                    self.session_manager.touch(session_uuid)
                elif not adapter.is_alive():
                    self.session_manager.reconcile_transport(session_uuid, reason="Session disconnected by device")
                    return
                else:
                    await asyncio.sleep(0)
        except Exception:
            if self.session_manager.get_session(session_uuid) is not None:
                self.session_manager.reconcile_transport(session_uuid, reason="WebSocket/transport failure")
