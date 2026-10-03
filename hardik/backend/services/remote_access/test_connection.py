"""One-shot validation of a device's Remote Access connection."""
from __future__ import annotations

import ipaddress
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from backend.models import Device
from backend.services.remote_access.ssh_service import SSHConnectionAdapter, SSHConnectionError
from backend.services.remote_access.telnet_service import TelnetConnectionAdapter
from backend.services.remote_access_credentials import RemoteAccessCredentialError, RemoteAccessCredentialService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TestConnectionRequest:
    __test__ = False
    device_id: int
    protocol: str
    username: str
    secret: str
    port: int | None = None
    remember_credential: bool = False
    auth_type: str = "password"


class TestConnectionService:
    """Validate a device endpoint and optionally remember its credential."""

    __test__ = False

    _ADAPTERS: dict[str, Callable[..., Any]] = {
        "ssh": SSHConnectionAdapter,
        "telnet": TelnetConnectionAdapter,
    }

    def __init__(self, db, *, adapter_factories: dict[str, Callable[..., Any]] | None = None, timeout: float = 10.0):
        self.db = db
        self.credentials = RemoteAccessCredentialService(db)
        self.adapter_factories = adapter_factories or self._ADAPTERS
        self.timeout = timeout

    def test_connection(self, request: TestConnectionRequest) -> dict[str, Any]:
        started = time.monotonic()
        protocol = request.protocol.lower() if isinstance(request.protocol, str) else request.protocol
        host: str | None = None
        port = request.port
        adapter = None
        credential = None
        logger.info("Remote Access test request: device_id=%s protocol=%s port=%s username_present=%s secret_present=%s credential_id=%s auth_type=%s remember_credential=%s",
                    request.device_id, protocol, port, bool(request.username), bool(request.secret), None, request.auth_type, request.remember_credential)
        try:
            device = self.db.get(Device, request.device_id)
            if device is None:
                return self._failure(protocol, host, port, started, "DEVICE_NOT_FOUND", "Device does not exist")
            host = device.ip_address
            logger.info("Remote Access test resolved device_id=%s ip=%s", request.device_id, host)
            try:
                ipaddress.ip_address(host)
            except ValueError:
                return self._failure(protocol, host, port, started, "INVALID_DEVICE_IP", "Device IP address is invalid")
            if protocol not in self.credentials.PROTOCOLS:
                return self._failure(protocol, host, port, started, "INVALID_PROTOCOL", "Protocol must be ssh or telnet")
            port = self.credentials.DEFAULT_PORTS[protocol] if request.port is None else request.port
            if not isinstance(port, int) or not 1 <= port <= 65535:
                return self._failure(protocol, host, port, started, "INVALID_PORT", "Port must be between 1 and 65535")
            if not isinstance(request.username, str) or not request.username.strip():
                return self._failure(protocol, host, port, started, "INVALID_USERNAME", "Username is required")
            if not isinstance(request.secret, str) or not request.secret:
                return self._failure(protocol, host, port, started, "SECRET_REQUIRED", "Authentication secret is required")
            if request.auth_type != "password":
                return self._failure(protocol, host, port, started, "INVALID_AUTH_TYPE", "Unsupported authentication type")

            factory = self.adapter_factories[protocol]
            adapter = factory(host, port, request.username.strip(), request.secret, timeout=self.timeout)
            logger.info("Remote Access test adapter connect START device_id=%s protocol=%s port=%s", request.device_id, protocol, port)
            adapter.connect()
            logger.info("Remote Access test adapter connect SUCCESS device_id=%s protocol=%s port=%s", request.device_id, protocol, port)
            metadata = dict(getattr(adapter, "metadata", {}) or {})
            metadata.update({"transport_validated": True, "shell_validated": protocol == "ssh"})
            if request.remember_credential:
                credential = self.credentials.upsert(device_id=device.id, protocol=protocol, port=port,
                                                      username=request.username.strip(), auth_type=request.auth_type,
                                                      secret=request.secret)
                credential = self.credentials.mark_verified(credential.id)
                logger.info(
                    "Remote Access credential saved: credential_persisted=true credential_id=%s device_id=%s protocol=%s verified=%s port=%s",
                    credential.id, credential.device_id, credential.protocol,
                    credential.is_verified, credential.port,
                )
            else:
                existing = self.credentials.get(device_id=device.id, protocol=protocol)
                if existing is not None and existing.is_verified:
                    credential = existing
            return {"success": True, "protocol": protocol, "host": host, "port": port,
                    "latency": self._latency(started), "connection_metadata": metadata,
                    "error_code": None, "message": None,
                    "credential_id": credential.id if credential is not None else None}
        except (ConnectionError, OSError, ValueError, KeyError, RemoteAccessCredentialError) as exc:
            if host is not None and protocol in self.credentials.PROTOCOLS:
                existing = self.credentials.get(device_id=request.device_id, protocol=protocol)
                if existing is not None:
                    self.credentials.mark_verification_failed(existing.id)
            code = self._error_code(exc)
            stage = getattr(exc, "stage", None) or ("SSH_HANDSHAKE" if protocol == "ssh" else "TCP_CONNECT")
            logger.warning("Remote Access test FAILED device_id=%s ip=%s protocol=%s port=%s stage=%s code=%s",
                           request.device_id, host, protocol, port, stage, code)
            return self._failure(protocol, host, port, started, code, self._safe_message(exc), stage)
        except Exception as exc:
            # Paramiko can raise implementation-specific exceptions while loading
            # host keys or negotiating. Keep SSH diagnostics structured and safe.
            if host is not None and protocol == "ssh":
                logger.warning("Remote Access test FAILED device_id=%s ip=%s protocol=ssh port=%s stage=SSH_HANDSHAKE code=SSH_HANDSHAKE_FAILED exception_type=%s",
                               request.device_id, host, port, type(exc).__name__)
                return self._failure(protocol, host, port, started, "SSH_HANDSHAKE_FAILED", "SSH handshake failed", "SSH_HANDSHAKE")
            raise
        finally:
            if adapter is not None:
                try:
                    adapter.disconnect()
                except Exception:
                    pass

    @staticmethod
    def _latency(started: float) -> float:
        return round(max(0.0, (time.monotonic() - started) * 1000), 3)

    def _failure(self, protocol, host, port, started, code, message, stage=None):
        return {"success": False, "protocol": protocol, "host": host, "port": port,
                "latency": self._latency(started), "connection_metadata": {},
                "error_code": code, "stage": stage, "message": message}

    @staticmethod
    def _error_code(exc: Exception) -> str:
        return getattr(exc, "code", "CONNECTION_FAILED")

    @staticmethod
    def _safe_message(exc: Exception) -> str:
        # Adapter/service messages are deliberately generic; never expose exception reprs.
        return getattr(exc, "message", "Connection validation failed")
