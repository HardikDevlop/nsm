"""SNMP security protocol normalization."""

AUTH_PROTOCOLS = {"sha": "usmHMACSHAAuthProtocol", "md5": "usmHMACMD5AuthProtocol"}
PRIVACY_PROTOCOLS = {
    "aes": "usmAesCfb128Protocol", "aes128": "usmAesCfb128Protocol",
    "des": "usmDESPrivProtocol",
}


def protocol_name(value: str | None) -> str | None:
    """Return a canonical lower-case protocol key for user input."""
    return value.lower().replace("-", "") if value else None
