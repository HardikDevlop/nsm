"""One-shot Linux firewall/security log collection over SSH.

Only explicit log indicators are converted into events.  This module does
not infer attacks from ordinary traffic and does not inspect SNMP collectors.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


class LinuxSecurityCollectionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_TIMESTAMP_ISO = re.compile(r"^(?P<value>\d{4}-\d{2}-\d{2}[T ][^ ]+)")
_TIMESTAMP_SYSLOG = re.compile(r"^(?P<value>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})")
_IP = r"(?P<value>\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]+)"


def _timestamp(line: str) -> datetime | None:
    match = _TIMESTAMP_ISO.search(line) or _TIMESTAMP_SYSLOG.search(line)
    if not match:
        return None
    raw = match.group("value")
    try:
        if raw[0].isalpha():
            parsed = datetime.strptime(f"{datetime.now().year} {raw}", "%Y %b %d %H:%M:%S")
            return parsed
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.astimezone(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _field(line: str, names: tuple[str, ...]) -> str | None:
    for name in names:
        match = re.search(rf"(?:^|\s){re.escape(name)}[=:](\S+)", line, re.IGNORECASE)
        if match:
            return match.group(1).strip("[](),")
    return None


def _valid_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        return None


def _event_from_line(line: str) -> dict[str, Any] | None:
    lowered = line.lower()
    port_scan = any(pattern in lowered for pattern in (
        "port scan", "portscan", "scan detected", "nmap scan", "masscan", "syn scan",
    ))
    firewall_block = (
        "[ufw block]" in lowered
        or bool(re.search(r"(?:iptables|ip6tables|nft).*(?:drop|reject|deny)", lowered))
        or bool(re.search(r"(?:firewall|security group).*(?:block|drop|reject|deny)", lowered))
    )
    if not port_scan and not firewall_block:
        return None

    destination_port_raw = _field(line, ("DPT", "dport", "dest_port", "destination_port"))
    try:
        destination_port = int(destination_port_raw) if destination_port_raw else None
    except ValueError:
        destination_port = None
    event_type = "port_scan" if port_scan else "firewall_block"
    # SNMP packets are not attacks merely because they appear in a log.  A
    # port-scan event explicitly targeting SNMP is retained only when the log
    # itself says it is a scan; ordinary SNMP traffic never matches above.
    if event_type == "port_scan" and destination_port in {161, 162} and "scan" not in lowered:
        return None
    severity_match = re.search(r"(?:severity|level)\s*[=:]\s*(critical|high|medium|low|warning|info)", lowered)
    severity = severity_match.group(1) if severity_match else None
    return {
        "event_timestamp": _timestamp(line),
        "source_ip": _valid_ip(_field(line, ("SRC", "src", "source", "source_ip"))),
        "destination_ip": _valid_ip(_field(line, ("DST", "dst", "destination", "destination_ip"))),
        "destination_port": destination_port,
        "event_type": event_type,
        "severity": severity,
        "raw_message": line[:4000],
    }


def parse_security_log(output: str, max_events: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in output.splitlines():
        event = _event_from_line(line.strip())
        if not event or event["event_timestamp"] is None:
            continue
        fingerprint = hashlib.sha256(
            f"{event['event_timestamp'].isoformat()}|{event['event_type']}|{event['raw_message']}".encode()
        ).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        event["event_hash"] = fingerprint
        events.append(event)
        if len(events) >= max_events:
            break
    return events


_LOG_COMMAND = r"""printf '__JOURNAL__\n'; if command -v journalctl >/dev/null 2>&1; then journalctl --since '__LOOKBACK__ minutes ago' --no-pager -n 1000 -o short-iso -k 2>/dev/null; journalctl --since '__LOOKBACK__ minutes ago' --no-pager -n 1000 -o short-iso -u ufw 2>/dev/null; fi; printf '__FILES__\n'; for f in /var/log/ufw.log /var/log/kern.log /var/log/messages /var/log/auth.log; do if [ -r "$f" ]; then tail -n 1000 "$f"; fi; done"""


def collect_security_logs(host: str, ssh_port: int, request: Any) -> tuple[list[dict[str, Any]], bool, list[str]]:
    try:
        import paramiko
    except ImportError as exc:
        raise LinuxSecurityCollectionError("unavailable", "Linux security collection requires the paramiko dependency") from exc

    if request.auth_method == "password" and request.password is None:
        raise LinuxSecurityCollectionError("authentication_failed", "password is required for password authentication")
    if request.auth_method == "ssh_key" and not request.private_key_path:
        raise LinuxSecurityCollectionError("authentication_failed", "private_key_path is required for ssh_key authentication")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        kwargs: dict[str, Any] = {
            "hostname": host,
            "port": ssh_port,
            "username": request.username,
            "timeout": request.timeout_seconds,
            "banner_timeout": request.timeout_seconds,
            "auth_timeout": request.timeout_seconds,
            "look_for_keys": request.auth_method in {"ssh_key", "agent"},
            "allow_agent": request.auth_method == "agent",
        }
        if request.auth_method == "password":
            kwargs["password"] = request.password.get_secret_value()
        elif request.private_key_path:
            kwargs["key_filename"] = request.private_key_path
        client.connect(**kwargs)
        command = _LOG_COMMAND.replace("__LOOKBACK__", str(request.lookback_minutes))
        _stdin, stdout, stderr = client.exec_command(command, timeout=request.timeout_seconds)
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace").strip()
        log_lines = [line.strip() for line in output.splitlines() if line.strip() not in {"__JOURNAL__", "__FILES__"}]
        available = bool(log_lines)
        warnings = [error[:500]] if error else []
        return parse_security_log(output, request.max_events), available, warnings
    except LinuxSecurityCollectionError:
        raise
    except paramiko.AuthenticationException as exc:
        raise LinuxSecurityCollectionError("authentication_failed", "SSH authentication failed") from exc
    except (paramiko.SSHException, OSError, EOFError) as exc:
        raise LinuxSecurityCollectionError("unavailable", f"Security log collection unavailable: {exc}") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise LinuxSecurityCollectionError("timeout", "Security log collection timed out") from exc
    finally:
        client.close()
