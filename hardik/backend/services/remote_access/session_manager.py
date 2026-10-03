"""Lifecycle manager for live Remote Access sessions.

The registry is intentionally owned by a ``SessionManager`` instance rather
than held in a module global. It is suitable for the current single-process
runtime; a multi-worker deployment must move this registry and ownership
coordination to a shared session broker before sessions can be worker-agnostic.
"""
from __future__ import annotations

import ipaddress
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from backend.models import Device, RemoteAccessSession, SSHHostKey, utc_now
from sqlalchemy.exc import SQLAlchemyError
from backend.services.remote_access.test_connection import TestConnectionService
from backend.services.remote_access_credentials import RemoteAccessCredentialError, RemoteAccessCredentialService

logger = logging.getLogger(__name__)


@dataclass
class ManagedSession:
    record: RemoteAccessSession
    adapter: Any
    # Bounded replay buffer lets a new browser attachment restore recent CLI
    # output without persisting credentials or unbounded terminal data.
    output_history: bytearray


class SessionManager:
    """Create, track, and close one persistent adapter per session."""

    DEFAULT_IDLE_TIMEOUT = timedelta(minutes=30)
    _ADAPTERS: dict[str, Callable[..., Any]] = TestConnectionService._ADAPTERS

    def __init__(self, db, *, adapter_factories: dict[str, Callable[..., Any]] | None = None,
                 idle_timeout: timedelta | float | int = DEFAULT_IDLE_TIMEOUT, timeout: float = 10.0):
        self.db = db
        self.credentials = RemoteAccessCredentialService(db)
        self.adapter_factories = adapter_factories or self._ADAPTERS
        self.timeout = timeout
        self.idle_timeout = timedelta(seconds=idle_timeout) if isinstance(idle_timeout, (int, float)) else idle_timeout
        if self.idle_timeout.total_seconds() <= 0:
            raise ValueError("idle_timeout must be positive")
        self._sessions: dict[str, ManagedSession] = {}

    def create_session(self, *, device_id: int, user_id: int, protocol: str,
                       credential_id: int | None = None, username: str | None = None,
                       secret: str | None = None, port: int | None = None,
                       source_ip: str | None = None) -> RemoteAccessSession:
        protocol = protocol.lower() if isinstance(protocol, str) else protocol
        logger.info(
            "Remote Access session request: device_id=%s protocol=%s port=%s credential_supplied=%s",
            device_id, protocol, port, credential_id is not None,
        )
        device = self.db.get(Device, device_id)
        if device is None:
            logger.warning("Remote Access session validation failed: code=DEVICE_NOT_FOUND device_id=%s", device_id)
            raise RemoteAccessCredentialError("DEVICE_NOT_FOUND", "Device does not exist")
        try:
            ipaddress.ip_address(device.ip_address)
        except ValueError as exc:
            logger.warning("Remote Access session validation failed: code=INVALID_DEVICE_IP device_id=%s", device_id)
            raise RemoteAccessCredentialError("INVALID_DEVICE_IP", "Device IP address is invalid") from exc
        if protocol not in self.credentials.PROTOCOLS:
            logger.warning("Remote Access session validation failed: code=INVALID_PROTOCOL protocol=%s", protocol)
            raise RemoteAccessCredentialError("INVALID_PROTOCOL", "Protocol must be ssh or telnet")

        saved = self.credentials.get_by_id(credential_id) if credential_id is not None else None
        logger.info(
            "Remote Access credential lookup: supplied=%s found=%s verified=%s",
            credential_id is not None, saved is not None, saved.is_verified if saved is not None else None,
        )
        if credential_id is not None and (saved is None or saved.device_id != device_id or saved.protocol != protocol):
            logger.warning(
                "Remote Access session validation failed: code=CREDENTIAL_NOT_FOUND device_id=%s protocol=%s "
                "credential_found=%s credential_device_matches=%s credential_protocol_matches=%s",
                device_id, protocol, saved is not None,
                saved is not None and saved.device_id == device_id,
                saved is not None and saved.protocol == protocol,
            )
            raise RemoteAccessCredentialError("CREDENTIAL_NOT_FOUND", "Credential does not exist")
        if saved is not None:
            if not saved.is_verified:
                logger.warning("Remote Access session validation failed: code=CREDENTIAL_NOT_VERIFIED credential_id_supplied=true")
                raise RemoteAccessCredentialError("CREDENTIAL_NOT_VERIFIED", "Credential is not verified")
            resolved = self.credentials.resolve_connection_credential(saved.id)
            logger.info("Remote Access credential resolved: credential_id=%s device_id=%s protocol=%s verified=%s port=%s",
                        saved.id, saved.device_id, saved.protocol, saved.is_verified, resolved.port)
            username, secret, port = resolved.username, resolved.secret, resolved.port
        elif username is None or secret is None:
            logger.warning("Remote Access session validation failed: code=CREDENTIAL_REQUIRED credential_supplied=false")
            raise RemoteAccessCredentialError("CREDENTIAL_REQUIRED", "A verified or temporary credential is required")

        port = self.credentials.DEFAULT_PORTS[protocol] if port is None else port
        if not isinstance(port, int) or not 1 <= port <= 65535:
            logger.warning("Remote Access session validation failed: code=INVALID_PORT protocol=%s port=%s", protocol, port)
            raise RemoteAccessCredentialError("INVALID_PORT", "Port must be between 1 and 65535")
        if not isinstance(username, str) or not username.strip():
            logger.warning("Remote Access session validation failed: code=INVALID_USERNAME")
            raise RemoteAccessCredentialError("INVALID_USERNAME", "Username is required")
        if not isinstance(secret, str) or not secret:
            logger.warning("Remote Access session validation failed: code=SECRET_REQUIRED")
            raise RemoteAccessCredentialError("SECRET_REQUIRED", "Authentication secret is required")

        # A remote device session is independent from browser attachments.  Reuse
        # the live adapter when another tab/browser asks for the same session.
        existing = (self.db.query(RemoteAccessSession)
                     .with_for_update()
                     .filter(RemoteAccessSession.device_id == device_id,
                             RemoteAccessSession.user_id == user_id,
                             RemoteAccessSession.protocol == protocol,
                             RemoteAccessSession.status.in_(("connecting", "connected")))
                     .order_by(RemoteAccessSession.id.desc()).first())
        if existing is not None:
            managed = self._sessions.get(existing.session_uuid)
            if managed is not None and managed.record.status in {"connecting", "connected"}:
                return existing
            # A process restart cannot safely claim an adapter it does not own.
            # Mark that stale durable row before creating the replacement.
            existing.status = "disconnected"
            existing.ended_at = existing.ended_at or utc_now()
            existing.disconnect_reason = "Backend session owner was lost"
            self.db.flush()

        now = utc_now()
        record = RemoteAccessSession(session_uuid=str(uuid.uuid4()), device_id=device_id,
                                     credential_id=saved.id if saved is not None else None,
                                     user_id=user_id, protocol=protocol, port=port,
                                     device_username=username.strip(), status="connecting",
                                     started_at=now, last_activity_at=now, source_ip=source_ip)
        self.db.add(record)
        self.db.flush()
        adapter = None
        try:
            adapter_kwargs = {"timeout": self.timeout}
            if protocol == "ssh":
                pinned = None
                # Do not use ``inspect(self.db.bind)`` here.  On SQLite with a
                # StaticPool (and on a few proxy dialects), inspection obtains
                # the same physical connection as this Session and rolls back
                # its transaction after PRAGMA table discovery.  That would
                # undo the CONNECTING INSERT before the CONNECTED UPDATE.
                connection = self.db.connection()
                if connection.dialect.has_table(connection, SSHHostKey.__table__.name):
                    pinned = self.db.query(SSHHostKey).filter_by(device_id=device.id, port=port, status="TRUSTED").first()
                if pinned is not None:
                    adapter_kwargs["expected_host_key_fingerprint"] = pinned.fingerprint
            adapter = self.adapter_factories[protocol](device.ip_address, port, username.strip(), secret,
                                                       **adapter_kwargs)
            adapter.connect()
            record.status = "connected"
            record.last_activity_at = utc_now()
            self.db.flush()
            self._sessions[record.session_uuid] = ManagedSession(record, adapter, bytearray())
            return record
        except Exception as exc:
            exception_message = str(exc)
            for sensitive_value in (username.strip(), secret):
                if sensitive_value:
                    exception_message = exception_message.replace(sensitive_value, "[REDACTED]")
            logger.exception(
                "Remote Access adapter connection failed: device_id=%s protocol=%s port=%s "
                "exception_type=%s exception_message=%s",
                device_id,
                protocol,
                port,
                type(exc).__name__,
                exception_message,
                exc_info=False,
            )
            if adapter is not None:
                self._close(adapter)
            # A failed adapter connection is still part of the caller's
            # transaction.  Preserve the durable FAILED state and leave the
            # commit/rollback decision to the route/service that owns `db`.
            # If the failure itself was a flush/DB error, the Session is in
            # pending-rollback state and a second flush would mask the real
            # database failure (and could affect unrelated caller work).
            if not isinstance(exc, SQLAlchemyError):
                record.status = "failed"
                record.ended_at = utc_now()
                code = getattr(exc, "code", "")
                record.disconnect_reason = {
                    "SSH_AUTH_FAILED": "Authentication failed",
                    "TCP_TIMEOUT": "Connection timed out",
                    "SSH_CHANNEL_CLOSED": "SSH channel closed",
                }.get(code, "Connection failed")
                self.db.flush()
            raise ConnectionError("Remote Access session could not be established") from exc

    def get_session(self, session_uuid: str) -> ManagedSession | None:
        return self._sessions.get(session_uuid)

    def list_active_sessions(self, *, user_id: int | None = None) -> list[RemoteAccessSession]:
        query = self.db.query(RemoteAccessSession).filter(RemoteAccessSession.status == "connected", RemoteAccessSession.ended_at.is_(None))
        if user_id is not None:
            query = query.filter(RemoteAccessSession.user_id == user_id)
        records = query.order_by(RemoteAccessSession.started_at.desc()).all()
        active = []
        for record in records:
            managed = self._sessions.get(record.session_uuid)
            if managed is None or not managed.adapter.is_alive():
                record.status = "disconnected"
                record.ended_at = record.ended_at or utc_now()
                record.disconnect_reason = "Backend session owner was lost"
            else:
                active.append(record)
        if records:
            self.db.flush()
        return active

    def touch(self, session_uuid: str) -> RemoteAccessSession:
        managed = self._required(session_uuid)
        if managed.record.status == "connected":
            managed.record.last_activity_at = utc_now()
            self.db.flush()
        return managed.record

    update_activity = touch

    def is_alive(self, session_uuid: str) -> bool:
        managed = self._sessions.get(session_uuid)
        return bool(managed and managed.record.status == "connected" and managed.adapter.is_alive())

    def disconnect_session(self, session_uuid: str, *, reason: str = "Disconnected") -> RemoteAccessSession:
        managed = self._sessions.get(session_uuid)
        if managed is None:
            record = self.db.query(RemoteAccessSession).filter_by(session_uuid=session_uuid).first()
            if record is None:
                raise KeyError("Session does not exist")
            return record
        if managed.record.status not in {"disconnected", "failed", "timeout"}:
            self._close(managed.adapter)
            managed.record.status = "disconnected"
            managed.record.ended_at = managed.record.ended_at or utc_now()
            managed.record.disconnect_reason = reason
            self.db.flush()
        self._sessions.pop(session_uuid, None)
        return managed.record

    def reconcile_transport(self, session_uuid: str, *, reason: str = "Connection lost") -> RemoteAccessSession | None:
        """Close a dead transport exactly once and persist its terminal state."""
        managed = self._sessions.get(session_uuid)
        if managed is None:
            return self.db.query(RemoteAccessSession).filter_by(session_uuid=session_uuid).first()
        if managed.record.status == "connected":
            self._close(managed.adapter)
            managed.record.status = "disconnected"
            managed.record.ended_at = managed.record.ended_at or utc_now()
            managed.record.disconnect_reason = reason
            self.db.flush()
        self._sessions.pop(session_uuid, None)
        return managed.record

    def cleanup_expired_sessions(self) -> list[str]:
        cutoff = utc_now() - self.idle_timeout
        expired = [item.record.session_uuid for item in self._sessions.values()
                   if item.record.status == "connected" and item.record.last_activity_at <= cutoff]
        for session_uuid in expired:
            managed = self._sessions[session_uuid]
            self._close(managed.adapter)
            managed.record.status = "timeout"
            managed.record.ended_at = utc_now()
            managed.record.disconnect_reason = "Idle timeout"
            self.db.flush()
            self._sessions.pop(session_uuid, None)
        return expired

    def _required(self, session_uuid: str) -> ManagedSession:
        managed = self._sessions.get(session_uuid)
        if managed is None:
            raise KeyError("Session does not exist")
        return managed

    @staticmethod
    def _close(adapter: Any) -> None:
        try:
            adapter.disconnect()
        except Exception:
            pass
