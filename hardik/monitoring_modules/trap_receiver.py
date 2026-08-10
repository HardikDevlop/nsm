"""Phase-4 SNMP trap receiver."""

from __future__ import annotations

import socket
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from config import EVENT_BUFFER_SIZE, TRAP_UDP_PORT

logger = logging.getLogger(__name__)


class TrapReceiver:
    """Receive and store SNMP trap payloads."""

    def __init__(self, max_events: int = EVENT_BUFFER_SIZE) -> None:
        self.events: deque[dict[str, Any]] = deque(maxlen=max_events)

    def ingest(self, payload: bytes | str, source_ip: str = "unknown") -> dict[str, Any]:
        """Store a decoded trap event."""
        event = self.parse(payload, source_ip)
        self.events.append(event)
        logger.info("trap_received source_ip=%s size_bytes=%s message=%s", source_ip, event["size_bytes"], event["message"][:200])
        return event

    def parse(self, payload: bytes | str, source_ip: str = "unknown") -> dict[str, Any]:
        """Create a normalized trap event.

        Full BER trap decoding can be plugged in later; the first product
        version keeps raw bytes and printable text for reliable event handling.
        """
        if isinstance(payload, str):
            raw_bytes = payload.encode("utf-8", errors="replace")
            text = payload
        else:
            raw_bytes = payload
            text = payload.decode("utf-8", errors="replace")

        return {
            "source": "snmp_trap",
            "source_ip": source_ip,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload_hex": raw_bytes.hex(),
            "message": text.strip(),
            "size_bytes": len(raw_bytes),
        }

    def drain(self) -> list[dict[str, Any]]:
        """Return buffered trap events without clearing them."""
        return list(self.events)

    def listen_once(self, host: str = "0.0.0.0", port: int = TRAP_UDP_PORT, timeout_seconds: float = 1.0) -> dict[str, Any] | None:
        """Receive one UDP trap packet."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout_seconds)
            sock.bind((host, port))
            try:
                payload, address = sock.recvfrom(8192)
            except socket.timeout:
                return None
        return self.ingest(payload, address[0])
