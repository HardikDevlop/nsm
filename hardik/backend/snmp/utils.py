"""Small SNMP utility functions."""


def mib_name(oid: str) -> str:
    """Return a safe display label for an OID without exposing it."""
    return oid.rsplit(".", 1)[-1]
