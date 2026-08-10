"""HTTP and HTTPS banner discovery."""

from __future__ import annotations

import re
import socket
import ssl
from typing import Any

from config import HTTP_TIMEOUT_SECONDS


HTTP_PORTS = {80: "http", 8080: "http", 443: "https", 8443: "https"}
TITLE_PATTERN = re.compile(r"<title[^>]*>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)
SERVER_PATTERN = re.compile(r"^server:\s*(?P<server>.+)$", re.IGNORECASE | re.MULTILINE)


class HTTPDiscovery:
    """Collect HTTP status line, server header, and page title."""

    def __init__(self, timeout_seconds: float = HTTP_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds

    def discover(self, ip_address: str, open_ports: dict[str, str] | None = None) -> dict[str, Any]:
        """Inspect HTTP-like ports that are already known to be open."""
        ports = self._candidate_ports(open_ports or {})
        banners: dict[str, dict[str, Any]] = {}
        for port, scheme in ports.items():
            banners[str(port)] = self._fetch(ip_address, port, scheme)
        return banners

    def _candidate_ports(self, open_ports: dict[str, str]) -> dict[int, str]:
        if not open_ports:
            return {}

        candidates: dict[int, str] = {}
        for port_text, service in open_ports.items():
            try:
                port = int(port_text)
            except ValueError:
                continue
            if port in HTTP_PORTS or "HTTP" in service.upper():
                candidates[port] = HTTP_PORTS.get(port, "https" if "HTTPS" in service.upper() else "http")
        return candidates

    def _fetch(self, ip_address: str, port: int, scheme: str) -> dict[str, Any]:
        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {ip_address}\r\n"
            "User-Agent: AgniGate-NMS/1.0\r\n"
            "Accept: text/html,*/*\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")

        try:
            raw = self._request(ip_address, port, scheme, request)
        except OSError as exc:
            return {"scheme": scheme, "status_line": None, "server": None, "title": None, "error": str(exc)}

        text = raw.decode("iso-8859-1", errors="replace")
        header_text, _, body = text.partition("\r\n\r\n")
        status_line = header_text.splitlines()[0] if header_text.splitlines() else None
        server_match = SERVER_PATTERN.search(header_text)
        title_match = TITLE_PATTERN.search(body)
        return {
            "scheme": scheme,
            "status_line": status_line,
            "server": server_match.group("server").strip() if server_match else None,
            "title": self._clean_title(title_match.group("title")) if title_match else None,
        }

    def _request(self, ip_address: str, port: int, scheme: str, request: bytes) -> bytes:
        with socket.create_connection((ip_address, port), timeout=self.timeout_seconds) as sock:
            sock.settimeout(self.timeout_seconds)
            stream: socket.socket | ssl.SSLSocket = sock
            if scheme == "https":
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                stream = context.wrap_socket(sock, server_hostname=ip_address)
            stream.sendall(request)
            return stream.recv(8192)

    @staticmethod
    def _clean_title(title: str) -> str:
        return re.sub(r"\s+", " ", title).strip()[:160]

