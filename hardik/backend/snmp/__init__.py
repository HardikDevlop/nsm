"""Canonical SNMP integration for the NMS backend.

The package owns transport, credentials, OID mapping, and normalization while
legacy discovery entry points remain compatible during migration.
"""

from .client import SNMPClient
from .collector import SNMPCollector
from .credentials import SNMPCredentials

__all__ = ["SNMPClient", "SNMPCollector", "SNMPCredentials"]
