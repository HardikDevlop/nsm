"""Polling cadence definitions used by the SNMP scheduler."""

POLL_INTERVALS = {
    "interfaces": 15,
    "cpu": 60,
    "memory": 60,
    "environment": 300,
    "lldp": 600,
    "routing": 600,
    "inventory": 86400,
}
