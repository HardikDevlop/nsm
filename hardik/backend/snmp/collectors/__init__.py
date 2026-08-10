"""
Agnigate NMS — SNMP Collectors
================================
All collectors are stateless, file-free, and multivendor.
OID knowledge comes exclusively from oid_catalog.py at runtime.
"""

from .base import (
    BaseCollector,
    CollectorResponse,
    CollectorResult,
    SNMPCollectorBase,
)
from .system      import SystemCollector
from .cpu         import CPUCollector
from .memory      import MemoryCollector
from .storage     import StorageCollector
from .interfaces  import InterfaceCollector
from .environment import EnvironmentCollector
from .vlan        import VLANCollector
from .lldp        import LLDPCollector
from .cdp         import CDPCollector
from .routing     import RoutingCollector
from .arp         import ARPCollector
from .mac_table   import MACTableCollector
from .firewall    import FirewallCollector
from .wireless    import WirelessCollector
from .inventory   import InventoryCollector
from .topology    import TopologyCollector
from .health      import HealthCollector

__all__ = [
    "BaseCollector", "CollectorResponse", "CollectorResult", "SNMPCollectorBase",
    "SystemCollector", "CPUCollector", "MemoryCollector", "StorageCollector",
    "InterfaceCollector", "EnvironmentCollector",
    "VLANCollector", "LLDPCollector", "CDPCollector",
    "RoutingCollector", "ARPCollector", "MACTableCollector",
    "FirewallCollector", "WirelessCollector",
    "InventoryCollector", "TopologyCollector", "HealthCollector",
]
