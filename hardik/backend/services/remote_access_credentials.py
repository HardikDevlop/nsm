"""Persistence and validation service for remote-access credentials.

This module deliberately has no connection or API concerns.  The only method
which returns a decrypted secret is ``resolve_connection_credential`` and it
returns an internal dataclass rather than an ORM object or response schema.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.models import Device, RemoteAccessCredential
from backend.utils.crypto import decrypt_secret, encrypt_secret
from backend.models import utc_now

Protocol = Literal["ssh", "telnet"]
AuthType = Literal["password", "private_key"]


class RemoteAccessCredentialError(ValueError):
    """Structured, client-safe service validation error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RemoteConnectionCredential:
    device_id: int
    protocol: Protocol
    host: str
    port: int
    username: str
    auth_type: AuthType
    secret: str


class RemoteAccessCredentialService:
    DEFAULT_PORTS = {"ssh": 22, "telnet": 23}
    PROTOCOLS = frozenset(DEFAULT_PORTS)
    AUTH_TYPES = frozenset(("password", "private_key"))

    def __init__(self, db: Session):
        self.db = db

    def _device(self, device_id: int) -> Device:
        device = self.db.get(Device, device_id)
        if device is None:
            raise RemoteAccessCredentialError("DEVICE_NOT_FOUND", "Device does not exist")
        return device

    @classmethod
    def _validate(cls, protocol: str, port: int | None, username: str | None,
                  auth_type: str | None, secret: str | None, *, require_secret: bool):
        if protocol not in cls.PROTOCOLS:
            raise RemoteAccessCredentialError("INVALID_PROTOCOL", "Protocol must be ssh or telnet")
        actual_port = cls.DEFAULT_PORTS[protocol] if port is None else port
        if not isinstance(actual_port, int) or not 1 <= actual_port <= 65535:
            raise RemoteAccessCredentialError("INVALID_PORT", "Port must be between 1 and 65535")
        if not isinstance(username, str) or not username.strip():
            raise RemoteAccessCredentialError("INVALID_USERNAME", "Username is required")
        if auth_type not in cls.AUTH_TYPES:
            raise RemoteAccessCredentialError("INVALID_AUTH_TYPE", "Unsupported authentication type")
        if require_secret and (not isinstance(secret, str) or not secret):
            raise RemoteAccessCredentialError("SECRET_REQUIRED", "Authentication secret is required")
        return actual_port, username.strip()

    def create(self, *, device_id: int, protocol: Protocol, username: str,
               auth_type: AuthType = "password", secret: str, port: int | None = None,
               created_by: int | None = None) -> RemoteAccessCredential:
        device = self._device(device_id)
        actual_port, username = self._validate(protocol, port, username, auth_type, secret, require_secret=True)
        item = RemoteAccessCredential(device_id=device.id, protocol=protocol, port=actual_port,
                                      username=username, auth_type=auth_type,
                                      encrypted_secret=encrypt_secret(secret), created_by=created_by,
                                      is_verified=False, last_verified_at=None)
        try:
            # A savepoint lets a concurrent unique-key loser recover without
            # rolling back the caller's surrounding transaction.
            with self.db.begin_nested():
                self.db.add(item)
                self.db.flush()
        except IntegrityError as exc:
            raise RemoteAccessCredentialError("CREDENTIAL_EXISTS", "Credential already exists for this device and protocol") from exc
        return item

    def upsert(self, **values) -> RemoteAccessCredential:
        protocol = values["protocol"]
        existing = self.get(device_id=values["device_id"], protocol=protocol)
        if existing:
            return self.update(existing.id, **{k: v for k, v in values.items() if k not in {"device_id", "protocol"}})
        try:
            return self.create(**values)
        except RemoteAccessCredentialError as exc:
            if exc.code != "CREDENTIAL_EXISTS":
                raise
            existing = self.get(device_id=values["device_id"], protocol=protocol)
            if existing:
                return self.update(existing.id, **{k: v for k, v in values.items() if k not in {"device_id", "protocol"}})
            raise

    def update(self, credential_id: int, *, port: int | None = None, username: str | None = None,
               auth_type: AuthType | None = None, secret: str | None = None) -> RemoteAccessCredential:
        item = self.get_by_id(credential_id)
        if item is None:
            raise RemoteAccessCredentialError("CREDENTIAL_NOT_FOUND", "Credential does not exist")
        new_port = item.port if port is None else port
        new_username = item.username if username is None else username
        new_auth = item.auth_type if auth_type is None else auth_type
        self._validate(item.protocol, new_port, new_username, new_auth, secret, require_secret=False)
        changed = (new_port != item.port or new_username.strip() != item.username or
                    new_auth != item.auth_type or secret is not None)
        item.port, item.username, item.auth_type = new_port, new_username.strip(), new_auth
        if secret is not None:
            item.encrypted_secret = encrypt_secret(secret)
        if changed:
            item.is_verified = False
            item.last_verified_at = None
        item.updated_at = utc_now()
        self.db.flush()
        return item

    def get_by_id(self, credential_id: int) -> RemoteAccessCredential | None:
        return self.db.get(RemoteAccessCredential, credential_id)

    def get(self, *, device_id: int, protocol: Protocol) -> RemoteAccessCredential | None:
        return self.db.query(RemoteAccessCredential).filter_by(device_id=device_id, protocol=protocol).first()

    def list(self, *, device_id: int | None = None) -> list[RemoteAccessCredential]:
        query = self.db.query(RemoteAccessCredential)
        if device_id is not None:
            query = query.filter(RemoteAccessCredential.device_id == device_id)
        return query.order_by(RemoteAccessCredential.id).all()

    def delete(self, credential_id: int) -> None:
        item = self.get_by_id(credential_id)
        if item is None:
            raise RemoteAccessCredentialError("CREDENTIAL_NOT_FOUND", "Credential does not exist")
        self.db.delete(item)
        self.db.flush()

    def mark_verified(self, credential_id: int) -> RemoteAccessCredential:
        item = self._required(credential_id)
        item.is_verified, item.last_verified_at = True, utc_now()
        self.db.flush()
        return item

    def mark_verification_failed(self, credential_id: int) -> RemoteAccessCredential:
        item = self._required(credential_id)
        item.is_verified, item.last_verified_at = False, None
        self.db.flush()
        return item

    def _required(self, credential_id: int) -> RemoteAccessCredential:
        item = self.get_by_id(credential_id)
        if item is None:
            raise RemoteAccessCredentialError("CREDENTIAL_NOT_FOUND", "Credential does not exist")
        return item

    def resolve_connection_credential(self, credential_id: int) -> RemoteConnectionCredential:
        item = self.db.query(RemoteAccessCredential).options(joinedload(RemoteAccessCredential.device)).filter_by(id=credential_id).first()
        if item is None:
            raise RemoteAccessCredentialError("CREDENTIAL_NOT_FOUND", "Credential does not exist")
        secret = decrypt_secret(item.encrypted_secret)
        if not secret:
            raise RemoteAccessCredentialError("CREDENTIAL_DECRYPTION_FAILED", "Credential secret could not be decrypted")
        return RemoteConnectionCredential(item.device_id, item.protocol, item.device.ip_address,
                                          item.port, item.username, item.auth_type, secret)
