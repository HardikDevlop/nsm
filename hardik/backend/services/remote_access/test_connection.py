"""One-shot validation of a device's Remote Access connection."""
from __future__ import annotations

import ipaddress
import logging
import time
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Callable

from backend.models import Device, SSHHostKey
from backend.services.remote_access.ssh_service import SSHConnectionAdapter, SSHConnectionError
from backend.services.remote_access.telnet_service import TelnetConnectionAdapter
from backend.services.remote_access_credentials import RemoteAccessCredentialError, RemoteAccessCredentialService
from backend.services.remote_access.host_keys import SSHHostKeyError, fetch_host_key
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TestConnectionRequest:
    __test__ = False
    device_id: int
    protocol: str
    username: str | None = None
    secret: str | None = None
    port: int | None = None
    remember_credential: bool = False
    auth_type: str = "password"
    mark_existing_failed: bool = True
    credential_id: int | None = None


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
        logger.info("Remote Access test request: device_id=%s protocol=%s port=%s credential_id=%s auth_type=%s remember_credential=%s",
                    request.device_id, protocol, port, request.credential_id, request.auth_type, request.remember_credential)
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
            if request.credential_id is not None:
                saved = self.credentials.get_by_id(request.credential_id)
                if saved is None or saved.device_id != device.id or saved.protocol != protocol:
                    return self._failure(protocol, host, port, started, "CREDENTIAL_NOT_FOUND", "Credential does not exist")
                resolved = self.credentials.resolve_connection_credential(saved.id)
                request_username, request_secret = resolved.username, resolved.secret
                port = resolved.port
            else:
                request_username, request_secret = request.username, request.secret
            if request.auth_type != "password":
                return self._failure(protocol, host, port, started, "INVALID_AUTH_TYPE", "Unsupported authentication type")

            factory = self.adapter_factories[protocol]
            adapter_kwargs = {"timeout": self.timeout}
            host_key = None
            # NMS host-key policy is deliberately only enabled when the
            # managed table exists. This keeps legacy/unit adapters usable
            # during migrations while never consulting OS known_hosts here.
            if protocol == "ssh" and inspect(self.db.bind).has_table(SSHHostKey.__tablename__):
                key_type, _public_key, fingerprint = fetch_host_key(host, port, self.timeout)
                host_key = self.db.query(SSHHostKey).filter_by(device_id=device.id, port=port).first()
                if host_key is None:
                    host_key = SSHHostKey(device_id=device.id, host=host, port=port,
                                         key_type=key_type, public_host_key=_public_key,
                                         fingerprint=fingerprint, status="PENDING")
                    self.db.add(host_key)
                    self.db.flush()
                    return self._failure(protocol, host, port, started, "HOST_KEY_UNKNOWN",
                                         "SSH host key requires review", "HOST_KEY_VERIFY",
                                         extra={"device_id": device.id, "requires_trust": True, "key_type": key_type,
                                                "fingerprint": fingerprint, "host_key_id": host_key.id})
                if host_key.status != "TRUSTED":
                    host_key.key_type, host_key.public_host_key = key_type, _public_key
                    host_key.fingerprint, host_key.scanned_at = fingerprint, datetime.utcnow()
                    self.db.flush()
                    return self._failure(protocol, host, port, started, "HOST_KEY_UNKNOWN",
                                         "SSH host key requires review", "HOST_KEY_VERIFY",
                                         extra={"device_id": device.id, "requires_trust": True, "key_type": key_type,
                                                "fingerprint": fingerprint, "host_key_id": host_key.id})
                if host_key.fingerprint != fingerprint:
                    return self._failure(protocol, host, port, started, "HOST_KEY_MISMATCH",
                                         "SSH host key does not match trusted key", "HOST_KEY_VERIFY",
                                         extra={"device_id": device.id, "requires_trust": False, "key_type": key_type,
                                                "stored_fingerprint": host_key.fingerprint,
                                                "received_fingerprint": fingerprint,
                                                "host_key_id": host_key.id})
                adapter_kwargs["expected_host_key_fingerprint"] = host_key.fingerprint
            if not isinstance(request_username, str) or not request_username.strip():
                if request.credential_id is None and request.username is not None:
                    return self._failure(protocol, host, port, started, "INVALID_USERNAME", "Username is required", "SSH_TRANSPORT_AUTH", extra={"device_id": device.id})
                return self._failure(protocol, host, port, started, "CREDENTIAL_REQUIRED", "Credentials are required after host-key verification", "SSH_TRANSPORT_AUTH", extra={"device_id": device.id})
            if not isinstance(request_secret, str) or not request_secret:
                if request.credential_id is None and request.secret is not None:
                    return self._failure(protocol, host, port, started, "SECRET_REQUIRED", "Authentication secret is required", "SSH_TRANSPORT_AUTH", extra={"device_id": device.id})
                return self._failure(protocol, host, port, started, "CREDENTIAL_REQUIRED", "Credentials are required after host-key verification", "SSH_TRANSPORT_AUTH", extra={"device_id": device.id})
            adapter = factory(host, port, request_username.strip(), request_secret, **adapter_kwargs)
            logger.info("Remote Access test adapter connect START device_id=%s protocol=%s port=%s", request.device_id, protocol, port)
            adapter.connect()
            logger.info("Remote Access test adapter connect SUCCESS device_id=%s protocol=%s port=%s", request.device_id, protocol, port)
            metadata = dict(getattr(adapter, "metadata", {}) or {})
            metadata.update({"transport_validated": True, "shell_validated": protocol == "ssh"})
            if request.remember_credential and request.credential_id is None:
                credential = self.credentials.upsert(device_id=device.id, protocol=protocol, port=port,
                    username=request_username.strip(), auth_type=request.auth_type,
                                                      secret=request_secret)
                credential = self.credentials.mark_verified(credential.id)
                logger.info(
                    "Remote Access credential saved: credential_persisted=true credential_id=%s device_id=%s protocol=%s verified=%s port=%s",
                    credential.id, credential.device_id, credential.protocol,
                    credential.is_verified, credential.port,
                )
            else:
                existing = self.credentials.get(device_id=device.id, protocol=protocol)
                # The connection just succeeded with the supplied credential;
                # expose the saved record without returning its secret.
                if existing is not None:
                    credential = existing
            return {"success": True, "protocol": protocol, "host": host, "port": port,
                    "latency": self._latency(started), "connection_metadata": metadata,
                    "error_code": None, "message": None,
                    "credential_id": credential.id if credential is not None else None}
        except (ConnectionError, OSError, ValueError, KeyError, RemoteAccessCredentialError) as exc:
            if request.mark_existing_failed and host is not None and protocol in self.credentials.PROTOCOLS:
                existing = self.credentials.get(device_id=request.device_id, protocol=protocol)
                if existing is not None:
                    self.credentials.mark_verification_failed(existing.id)
            code = self._error_code(exc)
            stage = getattr(exc, "stage", None) or ("HOST_KEY_VERIFY" if getattr(exc, "code", "").startswith("HOST_KEY") else ("SSH_HANDSHAKE" if protocol == "ssh" else "TCP_CONNECT"))
            logger.warning("Remote Access test FAILED device_id=%s ip=%s protocol=%s port=%s stage=%s code=%s",
                           request.device_id, host, protocol, port, stage, code)
            return self._failure(protocol, host, port, started, code, self._safe_message(exc), stage)
        except SQLAlchemyError as exc:
            logger.error("Remote Access test infrastructure failure: device_id=%s protocol=%s port=%s exception_type=%s",
                         request.device_id, protocol, port, type(exc).__name__)
            return self._failure(protocol, host, port, started, "INTERNAL_ERROR",
                                 "Remote Access validation is temporarily unavailable", "DATABASE")
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

    def _failure(self, protocol, host, port, started, code, message, stage=None, extra=None):
        result = {"success": False, "protocol": protocol, "host": host, "port": port,
                "latency": self._latency(started), "connection_metadata": {},
                "error_code": code, "stage": stage, "message": message}
        if extra:
            result.update(extra)
        return result

    @staticmethod
    def _error_code(exc: Exception) -> str:
        return getattr(exc, "code", "CONNECTION_FAILED")

    @staticmethod
    def _safe_message(exc: Exception) -> str:
        # Adapter/service messages are deliberately generic; never expose exception reprs.
        return getattr(exc, "message", "Connection validation failed")
