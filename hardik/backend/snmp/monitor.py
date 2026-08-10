"""SNMP monitoring facade backed by the enterprise service."""
from .collector import SNMPDiscovery

class SNMPMonitor:
    """Poll normalized SNMP data without v2c-only assumptions."""
    def __init__(self, **credentials):
        self.service = SNMPDiscovery(**credentials)
    def poll(self, ip_address: str) -> dict:
        return self.service.collect(ip_address)
