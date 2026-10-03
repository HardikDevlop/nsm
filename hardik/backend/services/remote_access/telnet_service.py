"""Raw, persistent Telnet terminal adapter.

Telnet is intentionally kept prompt-agnostic and unencrypted.  Authentication
handling belongs to a higher layer; this adapter only transports bytes and
answers Telnet option negotiation safely.
"""
from __future__ import annotations

import logging
import select
import socket
from typing import Any

logger = logging.getLogger(__name__)

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240


class TelnetConnectionError(ConnectionError):
    """A Telnet connection could not be established or used."""


class TelnetConnectionAdapter:
    """Persistent Telnet socket exposing raw device prompts and output."""

    security = "insecure_unencrypted"
    encrypted = False

    def __init__(self, host: str, port: int = 23, username: str = "", password: str = "", *, timeout: float = 10.0):
        if not host:
            raise ValueError("host is required")
        if not 1 <= port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.host, self.port = host, port
        self.username, self.password = username, password  # never submitted or logged here
        self.timeout = timeout
        self._socket: socket.socket | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        return {"protocol": "telnet", "encrypted": False, "security": self.security, "port": self.port}

    def connect(self) -> "TelnetConnectionAdapter":
        if self.is_alive():
            return self
        sock: socket.socket | None = None
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            sock.settimeout(self.timeout)
            self._socket = sock
            return self
        except (socket.timeout, TimeoutError) as exc:
            if sock:
                sock.close()
            raise TelnetConnectionError("Telnet connection timed out") from exc
        except (ConnectionRefusedError, OSError) as exc:
            if sock:
                sock.close()
            raise TelnetConnectionError("Telnet connection failed") from exc

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            raise TelnetConnectionError("Telnet connection is not connected")
        return self._socket

    def read(self, max_bytes: int = 65536, timeout: float = 0.0) -> bytes:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        sock = self._require_socket()
        wait = self.timeout if timeout is None else max(0.0, timeout)
        try:
            ready, _, _ = select.select([sock], [], [], wait)
            if not ready:
                return b""
            data = sock.recv(max_bytes)
            if not data:
                self.disconnect()
                return b""
            return self._negotiate(data)
        except socket.timeout:
            return b""
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            self.disconnect()
            raise TelnetConnectionError("Telnet connection was interrupted") from exc

    def _negotiate(self, data: bytes) -> bytes:
        """Strip Telnet commands and refuse option changes without credentials."""
        output, replies, index = bytearray(), bytearray(), 0
        while index < len(data):
            byte = data[index]
            if byte != IAC:
                output.append(byte); index += 1; continue
            if index + 1 >= len(data):
                raise TelnetConnectionError("Incomplete Telnet negotiation")
            command = data[index + 1]
            if command == IAC:
                output.append(IAC); index += 2; continue
            if command == SB:
                end = data.find(bytes((IAC, SE)), index + 2)
                if end < 0:
                    raise TelnetConnectionError("Incomplete Telnet subnegotiation")
                index = end + 2; continue
            if command in (DO, DONT, WILL, WONT):
                if index + 2 >= len(data):
                    raise TelnetConnectionError("Incomplete Telnet option negotiation")
                option = data[index + 2]
                replies.extend((IAC, WONT if command in (DO, DONT) else DONT, option))
                index += 3; continue
            raise TelnetConnectionError("Unsupported Telnet negotiation")
        if replies:
            try:
                self._require_socket().sendall(replies)
            except OSError as exc:
                self.disconnect()
                raise TelnetConnectionError("Telnet negotiation failed") from exc
        return bytes(output)

    def write(self, data: str | bytes) -> None:
        if not data:
            return
        try:
            self._require_socket().sendall(data.encode() if isinstance(data, str) else data)
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            self.disconnect()
            raise TelnetConnectionError("Could not write Telnet data") from exc

    def is_alive(self) -> bool:
        sock = self._socket
        if sock is None:
            return False
        try:
            return sock.fileno() >= 0
        except OSError:
            return False

    def disconnect(self) -> None:
        sock, self._socket = self._socket, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    close = disconnect

    def __enter__(self) -> "TelnetConnectionAdapter":
        return self.connect()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.disconnect()
