"""Phase-2 device profiler.

This module does not scan. It only receives normalized outputs from discovery
modules and turns those signals into a product-grade device profile.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any


CONFIDENCE_CAP = 98.6
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProfileEvidence:
    """One profiling signal and its weighted contribution."""

    field: str
    value: str
    score: float


class DeviceProfiler:
    """Build a normalized device profile from discovery module outputs."""

    def profile(self, discovery_outputs: dict[str, Any]) -> dict[str, Any]:
        """Return vendor/category/model/os/confidence without running scans."""
        ip_address = str(discovery_outputs.get("ip") or "")
        evidence = self._collect_evidence(discovery_outputs)

        vendor = self._best_value(evidence, "vendor") or "Unknown"
        category = self._best_value(evidence, "category") or "Unknown"
        model = self._best_value(evidence, "model") or "Unknown"
        operating_system = self._best_value(evidence, "os") or "Unknown"
        confidence = self._confidence(evidence, vendor, category, model, operating_system)
        logger.info("profile ip=%s vendor=%s category=%s model=%s os=%s confidence=%s", ip_address, vendor, category, model, operating_system, confidence)

        return {
            "ip": ip_address,
            "vendor": vendor,
            "category": category,
            "model": model,
            "os": operating_system,
            "confidence": confidence,
        }

    def _collect_evidence(self, data: dict[str, Any]) -> list[ProfileEvidence]:
        evidence: list[ProfileEvidence] = []
        open_ports = data.get("open_ports") or {}
        snmp = data.get("snmp") or {}
        http = data.get("http") or {}
        wmi = data.get("wmi") or {}
        ssh = data.get("ssh") or {}
        icmp = self._icmp_data(data)

        self._add_snmp_evidence(evidence, snmp)
        self._add_http_evidence(evidence, http)
        self._add_wmi_evidence(evidence, wmi)
        self._add_ssh_evidence(evidence, ssh)
        self._add_port_evidence(evidence, open_ports)
        self._add_icmp_evidence(evidence, icmp)
        return evidence

    def _add_snmp_evidence(self, evidence: list[ProfileEvidence], snmp: dict[str, Any]) -> None:
        if not snmp:
            return
        self._append(evidence, "vendor", snmp.get("vendor"), 36)
        self._append(evidence, "model", snmp.get("model"), 34)
        self._append(evidence, "os", snmp.get("firmware"), 24)
        sysdescr = str(snmp.get("sysDescr") or "")
        if sysdescr:
            self._append(evidence, "vendor", self._vendor_from_text(sysdescr), 30)
            self._append(evidence, "model", self._model_from_text(sysdescr), 28)
            self._append(evidence, "os", self._os_from_text(sysdescr), 22)
            self._append(evidence, "category", self._category_from_text(sysdescr), 20)

    def _add_http_evidence(self, evidence: list[ProfileEvidence], http: dict[str, Any]) -> None:
        text = self._http_text(http)
        if not text:
            return
        self._append(evidence, "vendor", self._vendor_from_text(text), 26)
        self._append(evidence, "model", self._model_from_text(text), 24)
        self._append(evidence, "os", self._os_from_text(text), 16)
        self._append(evidence, "category", self._category_from_text(text), 26)

    def _add_wmi_evidence(self, evidence: list[ProfileEvidence], wmi: dict[str, Any]) -> None:
        if not wmi.get("reachable"):
            return
        self._append(evidence, "vendor", wmi.get("manufacturer"), 34)
        self._append(evidence, "model", wmi.get("model"), 32)
        self._append(evidence, "os", wmi.get("os"), 36)
        self._append(evidence, "category", "Windows Server", 26)

    def _add_ssh_evidence(self, evidence: list[ProfileEvidence], ssh: dict[str, Any]) -> None:
        if not ssh.get("reachable"):
            return
        banner = str(ssh.get("banner") or ssh.get("server") or "")
        platform_hint = ssh.get("platform_hint")
        self._append(evidence, "os", platform_hint or self._os_from_text(banner) or "Linux / Unix", 22)
        self._append(evidence, "category", "Linux Server", 18)

    def _add_port_evidence(self, evidence: list[ProfileEvidence], open_ports: dict[str, str] | list[Any]) -> None:
        """Accept both legacy ``{port: service}`` and list-based port signals."""
        if isinstance(open_ports, dict):
            service_values = open_ports.values()
        elif isinstance(open_ports, list):
            service_values = (
                item.get("service", item.get("name", "")) if isinstance(item, dict) else item
                for item in open_ports
            )
        else:
            service_values = ()
        services = {str(service).upper() for service in service_values if service}
        if {"MS-RPC", "SMB", "RDP", "WINRM-HTTP", "WINRM-HTTPS"}.intersection(services):
            self._append(evidence, "category", "Windows Server", 20)
            self._append(evidence, "os", "Windows", 16)
        if "SSH" in services:
            self._append(evidence, "category", "Linux Server", 14)
        if "SNMP" in services:
            self._append(evidence, "category", "Network Device", 16)
        if {"HTTP", "HTTPS", "HTTP-ALT", "HTTPS-ALT"}.intersection(services):
            self._append(evidence, "category", "Web Device", 12)
        if {"MSSQL", "MYSQL", "ORACLE", "POSTGRESQL"}.intersection(services):
            self._append(evidence, "category", "Database Server", 22)
        if "PRINTER" in services:
            self._append(evidence, "category", "Printer", 28)

    def _add_icmp_evidence(self, evidence: list[ProfileEvidence], icmp: dict[str, Any]) -> None:
        estimated_os = icmp.get("estimated_os")
        if isinstance(estimated_os, dict):
            estimated_os = estimated_os.get("os")
        self._append(evidence, "os", estimated_os, 10)

    @staticmethod
    def _best_value(evidence: list[ProfileEvidence], field: str) -> str | None:
        totals: dict[str, float] = {}
        for item in evidence:
            if item.field == field:
                totals[item.value] = totals.get(item.value, 0) + item.score
        if not totals:
            return None
        return max(totals.items(), key=lambda item: item[1])[0]

    @staticmethod
    def _confidence(evidence: list[ProfileEvidence], vendor: str, category: str, model: str, operating_system: str) -> float:
        score = sum(item.score for item in evidence)
        completeness = sum(value != "Unknown" for value in (vendor, category, model, operating_system)) * 6.5
        confidence = min(CONFIDENCE_CAP, score + completeness)
        return round(confidence, 1)

    @staticmethod
    def _append(evidence: list[ProfileEvidence], field: str, value: Any, score: float) -> None:
        if value in (None, "", [], {}):
            return
        evidence.append(ProfileEvidence(field=field, value=str(value).strip(), score=score))

    @staticmethod
    def _icmp_data(data: dict[str, Any]) -> dict[str, Any]:
        return data.get("icmp") if isinstance(data.get("icmp"), dict) else data

    @staticmethod
    def _http_text(http: dict[str, Any]) -> str:
        values: list[str] = []
        for banner in http.values():
            if not isinstance(banner, dict):
                continue
            for key in ("server", "title", "status_line"):
                value = banner.get(key)
                if value:
                    values.append(str(value))
        return " ".join(values)

    @staticmethod
    def _vendor_from_text(text: str) -> str | None:
        for vendor in ("AgniGate", "Fortinet", "Cisco", "Juniper", "MikroTik", "Ubiquiti", "Dell", "HPE", "HP", "VMware"):
            if vendor.lower() in text.lower():
                return vendor
        return None

    @staticmethod
    def _model_from_text(text: str) -> str | None:
        patterns = [
            r"\b(GPZ\d{3,5})\b",
            r"\b(FG-[A-Za-z0-9-]+)\b",
            r"\b(ISR\s*[A-Za-z0-9-]+)\b",
            r"\b(EX\d{3,5})\b",
            r"\b(RB\d{3,5}[A-Za-z0-9-]*)\b",
            r"\b(USG-[A-Za-z0-9-]+)\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).replace(" ", "")
        return None

    @staticmethod
    def _os_from_text(text: str) -> str | None:
        lowered = text.lower()
        if "embedded linux" in lowered:
            return "Embedded Linux"
        if "linux" in lowered or "ubuntu" in lowered or "debian" in lowered:
            return "Linux"
        if "windows" in lowered:
            return "Windows"
        if "ios-xe" in lowered or "cisco ios" in lowered:
            return "Cisco IOS"
        if "junos" in lowered:
            return "Junos"
        if "routeros" in lowered:
            return "RouterOS"
        return None

    @staticmethod
    def _category_from_text(text: str) -> str | None:
        lowered = text.lower()
        if "firewall" in lowered or "security gateway" in lowered:
            return "Firewall"
        if "switch" in lowered:
            return "Switch"
        if "router" in lowered:
            return "Router"
        if "wireless" in lowered or "access point" in lowered:
            return "Access Point"
        if "printer" in lowered:
            return "Printer"
        if "server" in lowered:
            return "Server"
        return None
