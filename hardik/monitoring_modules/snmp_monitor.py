"""Deprecated import path retained for external callers.

The implementation lives exclusively in ``backend.snmp.monitor``.
"""
from backend.snmp.monitor import SNMPMonitor

__all__ = ["SNMPMonitor"]
