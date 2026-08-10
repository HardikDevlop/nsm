"""SNMP-specific exception types."""


class SNMPError(RuntimeError):
    """Base exception for normalized SNMP failures."""


class SNMPAuthenticationError(SNMPError):
    """Raised when an agent rejects credentials."""
