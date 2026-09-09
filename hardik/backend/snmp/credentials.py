"""Validated, transport-neutral SNMP credential data."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SNMPCredentials:
    """Connection settings for SNMPv2c or SNMPv3 USM."""

    version: str = "v2c"
    community: str | None = "public"
    username: str | None = None
    auth_protocol: str | None = None
    auth_password: str | None = None
    privacy_protocol: str | None = None
    privacy_password: str | None = None
    security_level: str | None = None
    port: int = 161

    def __post_init__(self) -> None:
        version = self.version.lower().replace("snmp", "")
        if version not in {"2c", "v2c", "3", "v3"}:
            raise ValueError("SNMP version must be v2c or v3")
        if version in {"3", "v3"} and not self.username:
            raise ValueError("SNMPv3 requires a username")
        if not 1 <= self.port <= 65535:
            raise ValueError("SNMP port must be between 1 and 65535")

    @property
    def is_v3(self) -> bool:
        return self.version.lower() in {"3", "v3"}
