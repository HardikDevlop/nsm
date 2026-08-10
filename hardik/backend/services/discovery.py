import ipaddress
import platform
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field


@dataclass
class ScanResult:
    ip_address: str
    hostname: str | None = None
    mac_address: str | None = None
    open_ports: list[int] = field(default_factory=list)
    snmp_name: str | None = None
    snmp_description: str | None = None


def _ping(ip: str, timeout_ms: int) -> bool:
    if platform.system().lower() == "windows":
        command = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        command = ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_ms / 1000 + 2)
        # Windows ping can exit 0 on "Destination host unreachable"
        return result.returncode == 0 and "ttl=" in result.stdout.lower()
    except (subprocess.TimeoutExpired, OSError):
        return False


def _scan_port(ip: str, port: int, timeout_ms: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout_ms / 1000)
            return sock.connect_ex((ip, port)) == 0
    except OSError:
        return False


def _resolve_hostname(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return None


def _lookup_mac(ip: str) -> str | None:
    """Read the local ARP/neighbour cache for the MAC address (works for LAN hosts).

    Uses `ip neigh show` on Linux (preferred) and falls back to `arp -a`
    on systems with net-tools installed.
    """
    # --- Linux: ip neigh (works without net-tools) ---
    try:
        output = subprocess.run(
            ["ip", "neigh", "show", ip],
            capture_output=True, text=True, timeout=5,
        ).stdout
        # Example: "192.168.100.1 dev eno1 lladdr 28:a9:15:06:0a:a4 REACHABLE"
        match = re.search(r"lladdr\s+([0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2}[-:][0-9a-fA-F]{2})", output)
        if match:
            return match.group(1).replace("-", ":").lower()
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass

    # --- Fallback: arp -a (needs net-tools) ---
    try:
        output = subprocess.run(
            ["arp", "-a", ip],
            capture_output=True, text=True, timeout=5,
        ).stdout
        match = re.search(r"([0-9a-fA-F]{2}[-:]){5}[0-9a-fA-F]{2}", output)
        if match:
            return match.group(0).replace("-", ":").lower()
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass

    return None


def _snmp_get(ip: str, community: str, timeout_ms: int) -> tuple[str | None, str | None]:
    """Fetch sysName/sysDescr through the shared v2c/v3 SNMP client."""
    try:
        from backend.snmp.collector import SNMPDiscovery
    except ImportError:
        return None, None
    try:
        client = SNMPDiscovery(communities=[community], timeout_seconds=timeout_ms / 1000)
        values = client.client.get(ip, ("1.3.6.1.2.1.1.5.0", "1.3.6.1.2.1.1.1.0"))
        return str(values.get("1.3.6.1.2.1.1.5.0") or "") or None, str(values.get("1.3.6.1.2.1.1.1.0") or "") or None
    except Exception:
        return None, None


def _scan_host(
    ip: str,
    ports: list[int],
    timeout_ms: int,
    snmp_community: str,
    scan_icmp: bool,
    scan_tcp_ports: bool,
    scan_snmp: bool,
) -> ScanResult | None:
    alive = _ping(ip, timeout_ms) if scan_icmp else False
    open_ports: list[int] = []
    if scan_tcp_ports:
        open_ports = [port for port in ports if _scan_port(ip, port, timeout_ms)]
    if not alive and not open_ports:
        return None
    result = ScanResult(ip_address=ip, open_ports=open_ports)
    result.hostname = _resolve_hostname(ip)
    result.mac_address = _lookup_mac(ip)
    if scan_snmp:
        result.snmp_name, result.snmp_description = _snmp_get(ip, snmp_community, timeout_ms)
    return result


def discover_network(
    network_range: str | None = None,
    ports: list[int] | None = None,
    timeout_ms: int = 700,
    snmp_community: str = "public",
    scan_icmp: bool = True,
    scan_tcp_ports: bool = True,
    scan_snmp: bool = False,
    max_hosts: int = 254,
    ip_list: list[str] | None = None,
) -> list[ScanResult]:
    """Scan a list of hosts (preferred) or a CIDR range.

    ``ip_list`` wins over ``network_range`` — callers that have already
    filtered out known-good devices should pass the pruned list here so
    that ``discover_network`` doesn't waste probes on them.
    """
    if ip_list:
        hosts = [str(ip) for ip in ip_list][:max_hosts]
    elif network_range:
        network = ipaddress.ip_network(network_range, strict=False)
        hosts = [str(host) for host in network.hosts()][:max_hosts]
        if not hosts:
            hosts = [str(network.network_address)]
    else:
        return []

    ports = ports or []

    results: list[ScanResult] = []
    with ThreadPoolExecutor(max_workers=64) as pool:
        futures = {
            pool.submit(
                _scan_host, ip, ports, timeout_ms, snmp_community, scan_icmp, scan_tcp_ports, scan_snmp
            ): ip
            for ip in hosts
        }
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)
    try:
        results.sort(key=lambda item: ipaddress.ip_address(item.ip_address))
    except ValueError:
        pass
    return results
