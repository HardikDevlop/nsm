"""SNMP transport adapter; pysnmp details are isolated here."""

from typing import Any

from .credentials import SNMPCredentials
from .security import AUTH_PROTOCOLS, PRIVACY_PROTOCOLS, protocol_name


class SNMPClient:
    """Execute SNMP GET and WALK operations with v2c/v3 credentials."""

    def __init__(self, credentials: SNMPCredentials, timeout: float = 2.0, retries: int = 1) -> None:
        self.credentials, self.timeout, self.retries = credentials, timeout, retries

    def _auth(self) -> Any:
        from pysnmp.hlapi.asyncio import CommunityData, UsmUserData
        if not self.credentials.is_v3:
            return CommunityData(self.credentials.community or "public", mpModel=1)
        
        import pysnmp.hlapi.asyncio as hlapi
        
        # Build kwargs only with non-None values to support all SNMPv3 security levels:
        # - noAuthNoPriv: No auth, no privacy (no kwargs added)
        # - authNoPriv: Auth only (authProtocol added, privProtocol omitted)
        # - authPriv: Auth + privacy (both protocols added)
        #
        # IMPORTANT: Do NOT pass security_level to UsmUserData - pysnmp infers it automatically
        # from the presence/absence of auth and privacy protocols.
        usmUserData_kwargs = {"userName": self.credentials.username or ""}
        
        if self.credentials.auth_protocol:
            auth_proto = getattr(hlapi, AUTH_PROTOCOLS[protocol_name(self.credentials.auth_protocol)])
            usmUserData_kwargs["authKey"] = self.credentials.auth_password
            usmUserData_kwargs["authProtocol"] = auth_proto
        
        if self.credentials.privacy_protocol:
            priv_proto = getattr(hlapi, PRIVACY_PROTOCOLS[protocol_name(self.credentials.privacy_protocol)])
            usmUserData_kwargs["privKey"] = self.credentials.privacy_password
            usmUserData_kwargs["privProtocol"] = priv_proto
        
        return UsmUserData(**usmUserData_kwargs)

    def get(self, host: str, oids: tuple[str, ...]) -> dict[str, Any]:
        """GET scalar OIDs and return stringified values keyed by OID."""
        import asyncio
        from pysnmp.hlapi.asyncio import ContextData, ObjectIdentity, ObjectType, SnmpEngine, UdpTransportTarget, getCmd
        async def run() -> Any:
            target = UdpTransportTarget((host, 161), timeout=self.timeout, retries=self.retries)
            return await getCmd(SnmpEngine(), self._auth(), target, ContextData(), *(ObjectType(ObjectIdentity(oid)) for oid in oids))
        indication, status, _, binds = asyncio.run(run())
        if indication or status:
            raise OSError(str(indication or status))
        return {str(oid): value.prettyPrint() for oid, value in binds}

    def walk(self, host: str, root_oid: str) -> dict[str, Any]:
        """Walk a table using the configured v2c/v3 security model."""
        import asyncio
        from pysnmp.hlapi.asyncio import ContextData, ObjectIdentity, ObjectType, SnmpEngine, UdpTransportTarget, walkCmd
        async def run() -> dict[str, Any]:
            result: dict[str, Any] = {}
            target = UdpTransportTarget((host, 161), timeout=self.timeout, retries=self.retries)
            async for indication, status, _, binds in walkCmd(SnmpEngine(), self._auth(), target, ContextData(), ObjectType(ObjectIdentity(root_oid)), lexicographicMode=False):
                if indication or status:
                    raise OSError(str(indication or status))
                result.update({str(oid): value.prettyPrint() for oid, value in binds})
            return result
        return asyncio.run(run())
