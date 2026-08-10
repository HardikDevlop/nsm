"""Phase-4 syslog collector."""

from __future__ import annotations

import re
import socket
from collections import deque
from datetime import datetime, timezone
from typing import Any

from config import EVENT_BUFFER_SIZE, SYSLOG_UDP_PORT


SYSLOG_PATTERN = re.compile(
    r"^(?:<(?P<priority>\d{1,3})>)?(?P<message>.*)$",
    re.DOTALL,
)


class SyslogCollector:
    """Parse and optionally collect syslog messages over UDP."""

    def __init__(self, max_events: int = EVENT_BUFFER_SIZE) -> None:
        self.events: deque[dict[str, Any]] = deque(maxlen=max_events)

    def ingest(self, message: str, source_ip: str = "unknown") -> dict[str, Any]:
        """Parse and store a syslog message."""
        event = self.parse(message, source_ip)
        self.events.append(event)
        return event

    def parse(self, message: str, source_ip: str = "unknown") -> dict[str, Any]:
        """Parse priority, facility, severity, and message body."""
        clean = message.strip()
        match = SYSLOG_PATTERN.match(clean)
        priority = int(match.group("priority")) if match and match.group("priority") else None
        severity = priority % 8 if priority is not None else None
        facility = priority // 8 if priority is not None else None
        body = match.group("message").strip() if match else clean
        return {
            "source": "syslog",
            "source_ip": source_ip,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "facility": facility,
            "severity": severity,
            "message": body,
            "raw": clean,
        }

    def drain(self) -> list[dict[str, Any]]:
        """Return buffered events without clearing them."""
        return list(self.events)

    def listen_once(self, host: str = "0.0.0.0", port: int = SYSLOG_UDP_PORT, timeout_seconds: float = 1.0) -> dict[str, Any] | None:
        """Receive one UDP syslog packet."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout_seconds)
            sock.bind((host, port))
            try:
                payload, address = sock.recvfrom(8192)
            except socket.timeout:
                return None
        return self.ingest(payload.decode("utf-8", errors="replace"), address[0])

