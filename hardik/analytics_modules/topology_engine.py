"""Phase-5 topology engine."""

from __future__ import annotations

import ipaddress
from typing import Any, Sequence


class TopologyEngine:
    """Infer topology nodes, links, and subnets from inventory records."""

    def build(self, devices: Sequence[dict[str, Any]]) -> dict[str, Any]:
        """Create a topology graph from inventory."""
        nodes = [self._node(device) for device in devices]
        links = self._links(nodes)
        subnets = self._subnets(nodes)
        return {"nodes": nodes, "links": links, "subnets": subnets}

    @staticmethod
    def _resolve_vendor(device: dict[str, Any]) -> str | None:
        """Best-effort vendor name for a device.

        Priority: explicit ``vendor`` field -> MAC OUI lookup -> ``None``.
        """
        explicit = device.get("vendor")
        if explicit and explicit != "Unknown":
            return explicit
        # Nested under device_profile / device
        for sub in ("device_profile", "device"):
            nested = device.get(sub)
            if isinstance(nested, dict):
                nested_vendor = nested.get("vendor")
                if nested_vendor and nested_vendor != "Unknown":
                    return nested_vendor
        # Fall back to MAC-based OUI lookup
        mac = (
            device.get("mac")
            or device.get("mac_address")
            or (device.get("arp") or {}).get("mac")
        )
        if mac:
            try:
                from vendor_map import lookup_vendor  # type: ignore

                resolved = lookup_vendor(mac)
                if resolved != "Unknown":
                    return resolved
            except Exception:
                return None
        return None

    def _node(self, device: dict[str, Any]) -> dict[str, Any]:
        details = device.get("device") or {}
        return {
            "id": device.get("ip") or device.get("ip_address"),
            "label": details.get("hostname") or device.get("hostname") or device.get("ip") or device.get("ip_address"),
            "category": details.get("category") or device.get("category") or device.get("device_type") or "Unknown",
            "vendor": self._resolve_vendor(device),
            "status": details.get("status") or device.get("status"),
            "ip": device.get("ip") or device.get("ip_address"),
            "mac": device.get("mac") or device.get("mac_address") or (device.get("arp") or {}).get("mac"),
        }

    def _links(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        gateways = [node for node in nodes if str(node.get("category", "")).lower() in {"firewall", "router", "network-device"}]
        if not gateways:
            return []

        gateway = sorted(gateways, key=lambda node: str(node.get("ip")))[0]
        links: list[dict[str, Any]] = []
        for node in nodes:
            if node["id"] == gateway["id"]:
                continue
            if self._same_slash24(gateway.get("ip"), node.get("ip")):
                links.append({"source": gateway["id"], "target": node["id"], "type": "inferred-l3"})
        return links

    @staticmethod
    def _subnets(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[str, int] = {}
        for node in nodes:
            try:
                network = ipaddress.ip_network(f"{node['ip']}/24", strict=False)
            except ValueError:
                continue
            key = str(network)
            buckets[key] = buckets.get(key, 0) + 1
        return [{"cidr": cidr, "device_count": count} for cidr, count in sorted(buckets.items())]

    @staticmethod
    def _same_slash24(left: Any, right: Any) -> bool:
        try:
            return ipaddress.ip_network(f"{left}/24", strict=False) == ipaddress.ip_network(f"{right}/24", strict=False)
        except ValueError:
            return False

