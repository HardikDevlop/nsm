"""One-shot Linux server detection over authenticated SSH plus an SNMP probe.

This module performs no scheduling and never writes to the database.  It only
returns data that was collected from the requested host.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any


class LinuxDetectionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _parse_os_release(value: str) -> tuple[str | None, str | None]:
    values: dict[str, str] = {}
    for line in value.splitlines():
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        values[key.strip()] = raw.strip().strip('"').strip("'")
    name = values.get("PRETTY_NAME") or values.get("NAME")
    version = values.get("VERSION_ID") or values.get("VERSION")
    return name, version


def _parse_interface_lines(value: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in value.splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        name, mac, state, mtu, speed, addresses = parts[:6]
        try:
            mtu_value = int(mtu)
        except ValueError:
            mtu_value = None
        try:
            speed_value = float(speed) if float(speed) >= 0 else None
        except ValueError:
            speed_value = None
        rows.append({
            "interface_name": name,
            "mac_address": mac or None,
            "ip_addresses": [item for item in addresses.split(",") if item],
            "state": state or None,
            "speed_mbps": speed_value,
            "mtu": mtu_value,
        })
    return rows


def _parse_disk_lines(value: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in value.splitlines():
        if not line or line.startswith("Filesystem"):
            continue
        parts = line.split()
        if len(parts) < 6:
            continue
        filesystem, total, used, available, usage, mount_point = parts[0:6]
        try:
            total_bytes = float(total)
            used_bytes = float(used)
            available_bytes = float(available)
        except ValueError:
            continue
        try:
            usage_percent = float(usage.rstrip("%"))
        except ValueError:
            usage_percent = None
        rows.append({
            "device": filesystem,
            "mount_point": mount_point,
            "filesystem": filesystem,
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
            "available_bytes": available_bytes,
            "usage_percent": usage_percent,
        })
    return rows


def _parse_probe_output(value: str) -> dict[str, Any]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in value.splitlines():
        if line.startswith("__") and line.endswith("__"):
            current = line
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    os_name, os_version = _parse_os_release("\n".join(sections.get("__OS__", [])))
    return {
        "hostname": "\n".join(sections.get("__HOST__", [])).strip(),
        "os_name": os_name,
        "os_version": os_version,
        "architecture": "\n".join(sections.get("__ARCH__", [])).strip() or None,
        "interfaces": _parse_interface_lines("\n".join(sections.get("__IFACES__", []))),
        "disks": _parse_disk_lines("\n".join(sections.get("__DISKS__", []))),
    }


_REMOTE_PROBE = r"""printf '__HOST__\n'; hostname; printf '__OS__\n'; cat /etc/os-release 2>/dev/null; printf '__ARCH__\n'; uname -m; printf '__IFACES__\n'; for d in /sys/class/net/*; do n=${d##*/}; mac=$(cat "$d/address" 2>/dev/null); state=$(cat "$d/operstate" 2>/dev/null); mtu=$(cat "$d/mtu" 2>/dev/null); speed=$(cat "$d/speed" 2>/dev/null); ips=$(ip -o addr show dev "$n" 2>/dev/null | awk '{print $4}' | paste -sd, -); printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$n" "$mac" "$state" "$mtu" "$speed" "$ips"; done; printf '__DISKS__\n'; df -P -B1 2>/dev/null || df -P"""


def _ssh_detect(request: Any) -> dict[str, Any]:
    try:
        import paramiko
    except ImportError as exc:
        raise LinuxDetectionError("unavailable", "Linux SSH detection requires the paramiko dependency") from exc

    try:
        ipaddress.ip_address(request.ip_address)
    except ValueError as exc:
        raise LinuxDetectionError("invalid_address", "ip_address must be a valid IP address") from exc

    if request.auth_method == "password" and request.password is None:
        raise LinuxDetectionError("authentication_failed", "password is required for password authentication")
    if request.auth_method == "ssh_key" and not request.private_key_path:
        raise LinuxDetectionError("authentication_failed", "private_key_path is required for ssh_key authentication")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        kwargs: dict[str, Any] = {
            "hostname": request.ip_address,
            "port": request.ssh_port,
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
        _stdin, stdout, stderr = client.exec_command(_REMOTE_PROBE, timeout=request.timeout_seconds)
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace").strip()
        if not output.strip():
            raise LinuxDetectionError("unavailable", error or "Linux probe returned no data")
        data = _parse_probe_output(output)
        if not data["hostname"]:
            raise LinuxDetectionError("unavailable", "Linux host did not return a hostname")
        data["ip_address"] = request.ip_address
        data["status"] = "active"
        return data
    except LinuxDetectionError:
        raise
    except paramiko.AuthenticationException as exc:
        raise LinuxDetectionError("authentication_failed", "SSH authentication failed") from exc
    except (paramiko.BadHostKeyException, paramiko.SSHException) as exc:
        raise LinuxDetectionError("unavailable", f"SSH connection unavailable: {exc}") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise LinuxDetectionError("timeout", "SSH connection or command timed out") from exc
    except (OSError, EOFError) as exc:
        raise LinuxDetectionError("unavailable", f"Linux server unavailable: {exc}") from exc
    finally:
        client.close()


async def _snmp_get(request: Any) -> bool:
    import pysnmp.hlapi.asyncio as hlapi

    from pysnmp.hlapi.asyncio import CommunityData, ContextData, ObjectIdentity, ObjectType, SnmpEngine, UdpTransportTarget, UsmUserData, getCmd

    if request.snmp_version == "v3":
        if not request.snmp_username:
            return False
        auth_protocol = (
            hlapi.usmHMACSHAAuthProtocol
            if request.snmp_auth_protocol == "sha"
            else hlapi.usmHMACMD5AuthProtocol
        )
        privacy_protocol = (
            hlapi.usmDESPrivProtocol
            if request.snmp_privacy_protocol == "des"
            else hlapi.usmAesCfb128Protocol
        )
        auth = UsmUserData(
            request.snmp_username,
            authProtocol=auth_protocol,
            authKey=request.snmp_auth_password.get_secret_value() if request.snmp_auth_password else None,
            privProtocol=privacy_protocol,
            privKey=request.snmp_privacy_password.get_secret_value() if request.snmp_privacy_password else None,
        )
    else:
        if request.snmp_community is None:
            return False
        auth = CommunityData(request.snmp_community.get_secret_value(), mpModel=1)
    target = UdpTransportTarget((request.ip_address, 161), timeout=request.timeout_seconds, retries=0)
    error_indication, error_status, _error_index, _var_binds = await getCmd(
        SnmpEngine(), auth, target, ContextData(), ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0"))
    )
    return not error_indication and not error_status


def detect_linux_server(request: Any) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {
        "ip_address": request.ip_address,
        "hostname": None,
        "interfaces": [],
        "disks": [],
        "status": "error",
        "ssh_valid": False,
        "snmp_valid": False,
    }
    warnings: list[str] = []
    try:
        data.update(_ssh_detect(request))
        data["ssh_valid"] = True
    except LinuxDetectionError as exc:
        data["ssh_error"] = exc.message
        warnings.append(f"SSH: {exc.message}")
    try:
        data["snmp_available"] = asyncio.run(asyncio.wait_for(_snmp_get(request), timeout=request.timeout_seconds + 1))
        data["snmp_valid"] = bool(data["snmp_available"])
        data["snmp_version"] = request.snmp_version if data["snmp_available"] else None
        if not data["snmp_available"]:
            data["snmp_error"] = "SNMPv3 did not respond with the supplied credentials"
            warnings.append(f"SNMPv3: {data['snmp_error']}")
    except (TimeoutError, asyncio.TimeoutError):
        data["snmp_available"] = False
        data["snmp_version"] = None
        data["snmp_error"] = "SNMPv3 probe timed out"
        warnings.append(f"SNMPv3: {data['snmp_error']}")
    except Exception as exc:
        data["snmp_available"] = False
        data["snmp_version"] = None
        data["snmp_error"] = f"SNMPv3 probe was unavailable: {exc}"
        warnings.append(f"SNMPv3: {data['snmp_error']}")
    data["status"] = "active" if data["ssh_valid"] and data["snmp_valid"] else "error"
    return data, warnings
