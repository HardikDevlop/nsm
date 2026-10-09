"""Lifecycle manager for live Remote Access sessions.

The registry is intentionally owned by a ``SessionManager`` instance rather
than held in a module global. It is suitable for the current single-process
runtime; a multi-worker deployment must move this registry and ownership
coordination to a shared session broker before sessions can be worker-agnostic.
"""
from __future__ import annotations

import ipaddress
import inspect
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from backend.models import Alert, Device, RemoteAccessSession, SSHHostKey, utc_now
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from backend.services.remote_access.test_connection import TestConnectionService
from backend.services.remote_access_credentials import RemoteAccessCredentialError, RemoteAccessCredentialService
from backend.services.alerting import _notify, prepare_notification_ids

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

    def _record_lifecycle_alert(self, record: RemoteAccessSession, *, connected: bool,
                                reason: str | None = None,
                                notification_ids: list[int] | None = None) -> None:
        """Persist a Remote Access lifecycle event through the normal alert path."""
        try:
            if not connected:
                self._log_disconnect_trigger(record, reason=reason, status_before=record.status)
            with self.db.begin_nested():
                device = self.db.get(Device, record.device_id)
                hostname = device.hostname if device is not None else str(record.device_id)
                protocol = record.protocol.upper()
                if connected:
                    title = f"Remote Access Connected: {hostname} ({protocol})"
                    description = (
                        f"{protocol} remote access session connected to {hostname}. "
                        f"User: {record.device_username}. Port: {record.port}."
                    )
                else:
                    title = f"Remote Access Disconnected: {hostname} ({protocol})"
                    description = (
                        f"{protocol} remote access session disconnected from {hostname}. "
                        f"User: {record.device_username}. Reason: {reason or 'Disconnected'}."
                    )
                alert = Alert(
                    device_id=record.device_id,
                    severity="info",
                    title=title,
                    description=description,
                    status="open",
                    created_at=utc_now(),
                )
                self.db.add(alert)
                self.db.flush()
                if notification_ids is None:
                    _notify(self.db, alert)
                else:
                    notification_ids.extend(prepare_notification_ids(self.db, alert))
        except Exception:
            # Remote access must remain usable if alert persistence or SMTP is
            # temporarily unavailable. The lifecycle event is best-effort.
            logger.exception(
                "Remote Access lifecycle alert could not be recorded: session=%s connected=%s",
                record.session_uuid,
                connected,
            )

    @staticmethod
    def _disconnect_trigger(reason: str | None, caller: str) -> str:
        reason_text = (reason or "").lower()
        if caller == "disconnect_session" or "client requested" in reason_text or "api disconnect" in reason_text:
            return "explicit_disconnect"
        if "idle" in reason_text or "timeout" in reason_text:
            return "health_check"
        if caller == "reconcile_transport":
            return "reconcile"
        if "websocket" in reason_text:
            return "websocket"
        if "lost" in reason_text or "device" in reason_text or "connection" in reason_text:
            return "adapter_failure"
        return "other"

    def _log_disconnect_trigger(self, record: RemoteAccessSession, *, reason: str | None,
                                status_before: str | None) -> None:
        """Temporary, credential-safe trace for every connected=False lifecycle alert."""
        frame = inspect.currentframe()
        caller = "unknown"
        chain = []
        if frame is not None:
            frame = frame.f_back
        while frame is not None and len(chain) < 8:
            name = frame.f_code.co_name
            if name not in {"_log_disconnect_trigger", "_record_lifecycle_alert"}:
                chain.append(f"{name}@{frame.f_code.co_filename}:{frame.f_lineno}")
                if caller == "unknown":
                    caller = name
            frame = frame.f_back
        trigger = self._disconnect_trigger(reason, caller)
        logger.warning(
            "REMOTE_ACCESS_DISCONNECT_TRIGGER session_uuid=%s current_status=%s ended_at=%s "
            "reason=%s caller=%s trigger=%s status_before=%s caller_chain=%s",
            record.session_uuid, record.status, record.ended_at, reason or "Disconnected",
            caller, trigger, status_before, " <- ".join(chain),
        )

    def _log_disconnect_request(self, record: RemoteAccessSession, *, reason: str,
                                caller: str) -> None:
        """Log the transition request before mutating the lifecycle state."""
        logger.warning(
            "REMOTE_ACCESS_DISCONNECT_TRIGGER session_uuid=%s current_status=%s ended_at=%s "
            "reason=%s caller=%s trigger=%s status_before=%s caller_chain=%s",
            record.session_uuid, record.status, record.ended_at, reason, caller,
            self._disconnect_trigger(reason, caller), record.status,
            f"{caller}@{inspect.currentframe().f_back.f_code.co_filename}:{inspect.currentframe().f_back.f_lineno}",
        )

    def _log_state_transition(self, record: RemoteAccessSession, *, status_before: str,
                              status_after: str,
                              reason: str | None, trigger: str, caller: str,
                              adapter: Any = None) -> None:
        adapter_present = adapter is not None
        try:
            adapter_alive = adapter.is_alive() if adapter_present else None
        except Exception:
            adapter_alive = "error"
        logger.warning(
            "REMOTE_ACCESS_STATE_TRANSITION session_uuid=%s status_before=%s status_after=%s "
            "started_at=%s ended_at=%s reason=%s trigger=%s caller=%s adapter_present=%s adapter_alive=%s",
            record.session_uuid, status_before, status_after, record.started_at,
            record.ended_at, reason or "", trigger, caller, adapter_present, adapter_alive,
        )

    def create_session(self, *, device_id: int, user_id: int, protocol: str,
                       credential_id: int | None = None, username: str | None = None,
                       secret: str | None = None, port: int | None = None,
                       source_ip: str | None = None,
                       remember_credential: bool = False) -> RemoteAccessSession:
        started = time.perf_counter()
        stage = "session-request"
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
            stage = "credential-resolved"
        elif username is None or secret is None:
            logger.warning("Remote Access session validation failed: code=CREDENTIAL_REQUIRED credential_supplied=false")
            raise RemoteAccessCredentialError("CREDENTIAL_REQUIRED", "A verified or temporary credential is required")

        elif username is not None and secret is not None:
            stage = "credential-resolved"
        logger.info("remote_access_stage device_id=%s protocol=%s stage=%s elapsed_ms=%.3f exception_class=None",
                    device_id, protocol, stage, (time.perf_counter() - started) * 1000)

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

        logger.info(
            "remote_access_stage user_id=%s device_id=%s protocol=%s stage=credential_validation duration_ms=%.3f",
            user_id, device_id, protocol, (time.perf_counter() - started) * 1000,
        )

        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(:user_id, :device_id)"),
                {"user_id": user_id, "device_id": device_id},
            )

        existing = (self.db.query(RemoteAccessSession)
                     .with_for_update()
                     .filter(RemoteAccessSession.device_id == device_id,
                             RemoteAccessSession.user_id == user_id,
                             RemoteAccessSession.status.in_(("connecting", "connected")))
                     .order_by(RemoteAccessSession.id.desc()).first())
        if existing is not None:
            managed = self._sessions.get(existing.session_uuid)
            try:
                still_connected = managed is not None and managed.record.status in {"connecting", "connected"} and managed.adapter.is_alive()
            except Exception:
                still_connected = False
            if still_connected:
                conflict = RemoteAccessCredentialError(
                    "DEVICE_ALREADY_CONNECTED",
                    "Device already has an active Remote Access session",
                )
                conflict.protocol = existing.protocol
                raise conflict
            # A process restart cannot safely claim an adapter it does not own.
            # Mark that stale durable row before creating the replacement.
            status_before = existing.status
            self._log_disconnect_request(existing, reason="Backend session owner was lost", caller="create_session")
            existing.status = "disconnected"
            existing.ended_at = existing.ended_at or utc_now()
            existing.disconnect_reason = "Backend session owner was lost"
            self._log_state_transition(
                existing, status_before=status_before, status_after="disconnected", reason=existing.disconnect_reason,
                trigger="stale_owner", caller="create_session", adapter=managed.adapter if managed else None,
            )
            self.db.flush()
            self._record_lifecycle_alert(existing, connected=False, reason=existing.disconnect_reason)
            if managed is not None:
                self._close(managed.adapter)
                self._sessions.pop(existing.session_uuid, None)

        now = utc_now()
        record = RemoteAccessSession(session_uuid=str(uuid.uuid4()), device_id=device_id,
                                     credential_id=saved.id if saved is not None else None,
                                     user_id=user_id, protocol=protocol, port=port,
                                     device_username=username.strip(), status="connecting",
                                     started_at=now, last_activity_at=now, source_ip=source_ip)
        self.db.add(record)
        self.db.flush()
        logger.info(
            "remote_access_stage user_id=%s device_id=%s protocol=%s stage=session_record_created duration_ms=%.3f",
            user_id, device_id, protocol, (time.perf_counter() - started) * 1000,
        )
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
                managed_host_key_table = connection.dialect.has_table(connection, SSHHostKey.__table__.name)
                if managed_host_key_table:
                    pinned = self.db.query(SSHHostKey).filter_by(device_id=device.id, port=port, status="TRUSTED").first()
                if managed_host_key_table and pinned is None:
                    raise RemoteAccessCredentialError("HOST_KEY_UNKNOWN", "SSH host key requires NMS trust")
                if pinned is not None:
                    adapter_kwargs["expected_host_key_fingerprint"] = pinned.fingerprint
            adapter = self.adapter_factories[protocol](device.ip_address, port, username.strip(), secret,
                                                       **adapter_kwargs)
            stage = "ssh-connected"
            handshake_started = time.perf_counter()
            adapter.connect()
            logger.info("remote_access_stage user_id=%s device_id=%s protocol=%s stage=ssh-connected elapsed_ms=%.3f exception_class=None",
                        user_id, device_id, protocol, (time.perf_counter() - handshake_started) * 1000)
            logger.info("remote_access_stage device_id=%s protocol=%s stage=ssh-authenticated elapsed_ms=%.3f exception_class=None",
                        device_id, protocol, (time.perf_counter() - started) * 1000)
            if remember_credential and saved is None:
                saved = self.credentials.upsert(
                    device_id=device_id,
                    protocol=protocol,
                    port=port,
                    username=username.strip(),
                    auth_type="password",
                    secret=secret,
                    created_by=user_id,
                )
                saved = self.credentials.mark_verified(saved.id)
                record.credential_id = saved.id
            record.status = "connected"
            record.last_activity_at = utc_now()
            self.db.flush()
            logger.info("remote_access_stage device_id=%s protocol=%s stage=db-session-created elapsed_ms=%.3f exception_class=None",
                        device_id, protocol, (time.perf_counter() - started) * 1000)
            self._sessions[record.session_uuid] = ManagedSession(record, adapter, bytearray())
            logger.info("remote_access_stage device_id=%s protocol=%s stage=shell-opened elapsed_ms=%.3f exception_class=None",
                        device_id, protocol, (time.perf_counter() - started) * 1000)
            logger.info(
                "remote_access_stage user_id=%s device_id=%s protocol=%s stage=session_ready duration_ms=%.3f",
                user_id, device_id, protocol, (time.perf_counter() - started) * 1000,
            )
            return record
        except Exception as exc:
            exception_message = str(exc)
            for sensitive_value in (username.strip(), secret):
                if sensitive_value:
                    exception_message = exception_message.replace(sensitive_value, "[REDACTED]")
            logger.exception(
                "Remote Access adapter connection failed: device_id=%s protocol=%s port=%s "
                "stage=%s elapsed_ms=%.3f exception_type=%s exception_message=%s",
                device_id,
                protocol,
                port,
                stage,
                (time.perf_counter() - started) * 1000,
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
                status_before = record.status
                record.status = "failed"
                record.ended_at = utc_now()
                code = getattr(exc, "code", "")
                record.disconnect_reason = {
                    "SSH_AUTH_FAILED": "Authentication failed",
                    "TCP_TIMEOUT": "Connection timed out",
                    "SSH_CHANNEL_CLOSED": "SSH channel closed",
                }.get(code, "Connection failed")
                self._log_state_transition(
                    record, status_before=status_before, status_after="failed", reason=record.disconnect_reason,
                    trigger="adapter_failure", caller="create_session", adapter=adapter,
                )
                try:
                    self.db.flush()
                except SQLAlchemyError:
                    self.db.rollback()
            # Preserve the safe, structured connection code for the API/UI.
            # Previously this generic wrapper discarded SSH_AUTH_FAILED,
            # HOST_KEY_UNKNOWN, TCP_TIMEOUT, etc. and every failure appeared
            # as SESSION_CREATE_FAILED.
            wrapped = ConnectionError("Remote Access session could not be established")
            wrapped.code = getattr(exc, "code", None) or "SESSION_CREATE_FAILED"
            if wrapped.code == "TCP_TIMEOUT":
                wrapped.code = "SSH_TIMEOUT"
            wrapped.stage = getattr(exc, "stage", None)
            raise wrapped from exc

    def get_session(self, session_uuid: str) -> ManagedSession | None:
        return self._sessions.get(session_uuid)

    def reconcile_stale_sessions_on_startup(self) -> int:
        """End durable sessions whose process-local transports cannot survive restart.

        Remote Access currently has one owning backend process. This operation is
        intentionally called only at that process startup boundary; GET/list
        operations remain non-destructive.
        """
        stale = (self.db.query(RemoteAccessSession)
                 .filter(RemoteAccessSession.status.in_(("connecting", "connected")))
                 .all())
        for record in stale:
            status_before = record.status
            record.status = "disconnected"
            record.ended_at = record.ended_at or utc_now()
            record.disconnect_reason = "Backend service restarted"
            self._log_state_transition(
                record, status_before=status_before, status_after="disconnected", reason=record.disconnect_reason,
                trigger="startup_reconciliation", caller="reconcile_stale_sessions_on_startup",
            )
        if stale:
            self.db.commit()
            logger.info("remote_access_startup_reconciliation count=%s reason=%s",
                        len(stale), "Backend service restarted")
        return len(stale)

    def list_active_sessions(self, *, user_id: int | None = None) -> list[RemoteAccessSession]:
        query = self.db.query(RemoteAccessSession).filter(RemoteAccessSession.status == "connected", RemoteAccessSession.ended_at.is_(None))
        if user_id is not None:
            query = query.filter(RemoteAccessSession.user_id == user_id)
        records = query.order_by(RemoteAccessSession.started_at.desc()).all()
        active = []
        for record in records:
            managed = self._sessions.get(record.session_uuid)
            # Listing is intentionally read-only when this process does not
            # own the runtime adapter. A durable CONNECTED row can belong to
            # another worker/process, or survive a browser detachment; neither
            # proves that the remote transport failed.
            if managed is None:
                active.append(record)
                continue
            if not managed.adapter.is_alive():
                status_before = record.status
                self._log_disconnect_request(record, reason="Adapter health check failed", caller="list_active_sessions")
                record.status = "disconnected"
                record.ended_at = record.ended_at or utc_now()
                record.disconnect_reason = "Adapter health check failed"
                self._log_state_transition(
                    record, status_before=status_before, status_after="disconnected", reason=record.disconnect_reason,
                    trigger="adapter_failure", caller="list_active_sessions", adapter=managed.adapter,
                )
                self._record_lifecycle_alert(record, connected=False, reason=record.disconnect_reason)
            else:
                active.append(record)
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

    def disconnect_session(self, session_uuid: str, *, reason: str = "Disconnected",
                           notification_ids: list[int] | None = None) -> RemoteAccessSession:
        started = time.perf_counter()
        logger.info("REMOTE_ACCESS_DISCONNECT_TIMING stage=disconnect-start session_uuid=%s", session_uuid)
        managed = self._sessions.get(session_uuid)
        if managed is None:
            record = self.db.query(RemoteAccessSession).filter_by(session_uuid=session_uuid).first()
            if record is None:
                raise KeyError("Session does not exist")
            return record
        if managed.record.status not in {"disconnected", "failed", "timeout"}:
            status_before = managed.record.status
            self._log_disconnect_request(managed.record, reason=reason, caller="disconnect_session")
            self._close(managed.adapter)
            logger.info("REMOTE_ACCESS_DISCONNECT_TIMING stage=adapter-closed session_uuid=%s elapsed_ms=%.3f",
                        session_uuid, (time.perf_counter() - started) * 1000)
            managed.record.status = "disconnected"
            managed.record.ended_at = managed.record.ended_at or utc_now()
            managed.record.disconnect_reason = reason
            self._log_state_transition(
                managed.record, status_before=status_before, status_after="disconnected", reason=reason,
                trigger="explicit_disconnect", caller="disconnect_session", adapter=managed.adapter,
            )
            self._record_lifecycle_alert(managed.record, connected=False, reason=reason,
                                         notification_ids=notification_ids)
            self.db.commit()
            logger.info("REMOTE_ACCESS_DISCONNECT_TIMING stage=state-persisted session_uuid=%s elapsed_ms=%.3f",
                        session_uuid, (time.perf_counter() - started) * 1000)
            if notification_ids is not None:
                logger.info("REMOTE_ACCESS_DISCONNECT_TIMING stage=notification-enqueued session_uuid=%s count=%s elapsed_ms=%.3f",
                            session_uuid, len(notification_ids), (time.perf_counter() - started) * 1000)
        self._sessions.pop(session_uuid, None)
        return managed.record

    def reconcile_transport(self, session_uuid: str, *, reason: str = "Connection lost") -> RemoteAccessSession | None:
        """Close a dead transport exactly once and persist its terminal state."""
        managed = self._sessions.get(session_uuid)
        if managed is None:
            return self.db.query(RemoteAccessSession).filter_by(session_uuid=session_uuid).first()
        if managed.record.status == "connected":
            status_before = managed.record.status
            self._log_disconnect_request(managed.record, reason=reason, caller="reconcile_transport")
            self._close(managed.adapter)
            managed.record.status = "disconnected"
            managed.record.ended_at = managed.record.ended_at or utc_now()
            managed.record.disconnect_reason = reason
            self._log_state_transition(
                managed.record, status_before=status_before, status_after="disconnected", reason=reason,
                trigger="adapter_failure", caller="reconcile_transport", adapter=managed.adapter,
            )
            self._record_lifecycle_alert(managed.record, connected=False, reason=reason)
            self.db.commit()
        self._sessions.pop(session_uuid, None)
        return managed.record

    def cleanup_expired_sessions(self) -> list[str]:
        cutoff = utc_now() - self.idle_timeout
        expired = [item.record.session_uuid for item in self._sessions.values()
                   if item.record.status == "connected" and item.record.last_activity_at <= cutoff]
        for session_uuid in expired:
            managed = self._sessions[session_uuid]
            status_before = managed.record.status
            self._log_disconnect_request(managed.record, reason="Idle timeout", caller="cleanup_expired_sessions")
            self._close(managed.adapter)
            managed.record.status = "timeout"
            managed.record.ended_at = utc_now()
            managed.record.disconnect_reason = "Idle timeout"
            self._log_state_transition(
                managed.record, status_before=status_before, status_after="timeout", reason=managed.record.disconnect_reason,
                trigger="health_check", caller="cleanup_expired_sessions", adapter=managed.adapter,
            )
            self._record_lifecycle_alert(managed.record, connected=False, reason="Idle timeout")
            self.db.flush()
            self._sessions.pop(session_uuid, None)
        if expired:
            self.db.commit()
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
