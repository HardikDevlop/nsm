"""WebSocket bridge for an already-created Remote Access session."""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

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
        # The browser must establish the xterm geometry before replaying any
        # buffered ANSI/cursor-positioned output. Replaying history first can
        # render a 120x40 PTY screen into a smaller xterm and leave apparent
        # blank rows/spacing behind. The first browser message is handled
        # synchronously; subsequent messages use the normal loop below.
        try:
            initial_message = await websocket.receive()
            if initial_message.get("type") == "websocket.disconnect":
                return
            await self._handle_message(websocket, session_uuid, managed.adapter, initial_message)
        except WebSocketDisconnect:
            return
        if managed.output_history:
            try:
                await websocket.send_bytes(bytes(managed.output_history))
            except Exception:
                # A browser attachment is disposable; a failed initial send
                # does not prove that the remote SSH transport ended.
                return
        reader = asyncio.create_task(self._forward_output(websocket, session_uuid, managed.adapter))
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                await self._handle_message(websocket, session_uuid, managed.adapter, message)
        except WebSocketDisconnect:
            # Browser refresh/navigation/close detaches only the WebSocket.
            # Keep the persistent remote session alive.
            pass
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
                old_cols = getattr(adapter, "width", None)
                old_rows = getattr(adapter, "height", None)
                if old_cols == cols and old_rows == rows:
                    return
                try:
                    await asyncio.to_thread(adapter.resize, cols, rows)
                except Exception:
                    logger.warning(
                        "REMOTE_ACCESS_PTY_RESIZE session_uuid=%s old_cols=%s old_rows=%s "
                        "new_cols=%s new_rows=%s success=False",
                        session_uuid, old_cols, old_rows, cols, rows,
                    )
                    raise
                logger.info(
                    "REMOTE_ACCESS_PTY_RESIZE session_uuid=%s old_cols=%s old_rows=%s "
                    "new_cols=%s new_rows=%s success=True",
                    session_uuid, old_cols, old_rows, cols, rows,
                )
                self.session_manager.touch(session_uuid)
            else:
                await websocket.send_json({"type": "resize_ack", "supported": False})
        elif kind == "ping":
            await websocket.send_json({"type": "pong"})
            self.session_manager.touch(session_uuid)
        elif kind == "disconnect":
            notification_ids: list[int] = []
            disconnect = self.session_manager.disconnect_session
            if "notification_ids" in inspect.signature(disconnect).parameters:
                disconnect(session_uuid, reason="Client requested disconnect", notification_ids=notification_ids)
            else:  # compatibility for lightweight/custom session manager implementations
                disconnect(session_uuid, reason="Client requested disconnect")
            if notification_ids:
                # Import lazily to avoid the route/service import cycle at module load.
                from backend.api.remote_access_routes import _deliver_remote_access_notifications
                asyncio.create_task(asyncio.to_thread(
                    _deliver_remote_access_notifications, list(notification_ids), session_uuid
                ))
            logger.info("REMOTE_ACCESS_DISCONNECT_TIMING stage=before-return/ws-close session_uuid=%s",
                        session_uuid)
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
                        # Do not terminate the remote session because the
                        # browser attachment disappeared or could not receive
                        # a frame. A later adapter read/health failure owns
                        # transport reconciliation.
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
