"""Compatibility facade for existing discovery callers.

This keeps the established result shape and API behavior while callers migrate
from the legacy module to ``backend.snmp``.
"""

from .collector import SNMPDiscovery
