from __future__ import annotations

import base64
import hashlib
import socket
from datetime import datetime

import paramiko
from sqlalchemy.orm import Session

from backend.models import Device, SSHHostKey
from backend.services.remote_access.ssh_service import _RemoteAccessTransport


class SSHHostKeyError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _fingerprint(key: paramiko.PKey) -> str:
    digest = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode("ascii").rstrip("=")
    return f"SHA256:{digest}"


def fetch_host_key(host: str, port: int, timeout: float = 10.0) -> tuple[str, str, str]:
    transport = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        transport = _RemoteAccessTransport(sock)
        transport.banner_timeout = timeout
        transport.start_client(timeout=timeout)
        key = transport.get_remote_server_key()
        return key.get_name(), base64.b64encode(key.asbytes()).decode("ascii"), _fingerprint(key)
    except (OSError, socket.timeout, paramiko.SSHException) as exc:
        raise SSHHostKeyError("HOST_KEY_SCAN_FAILED", "SSH host key scan failed") from exc
    finally:
        if transport is not None:
            transport.close()


class SSHHostKeyService:
    def __init__(self, db: Session):
        self.db = db

    def scan(self, device_id: int, port: int) -> SSHHostKey:
        device = self.db.get(Device, device_id)
        if device is None:
            raise SSHHostKeyError("DEVICE_NOT_FOUND", "Device does not exist")
        key_type, public_key, fingerprint = fetch_host_key(device.ip_address, port)
        item = self.db.query(SSHHostKey).filter_by(device_id=device_id, port=port).first()
        if item is None:
            item = SSHHostKey(device_id=device_id, host=device.ip_address, port=port)
            self.db.add(item)
        item.host, item.key_type, item.public_host_key = device.ip_address, key_type, public_key
        item.fingerprint, item.scanned_at = fingerprint, datetime.utcnow()
        if item.status != "TRUSTED":
            item.status, item.trusted_at, item.trusted_by = "PENDING", None, None
        self.db.flush()
        return item

    def trust(self, host_key_id: int, user_id: int) -> SSHHostKey:
        item = self.db.get(SSHHostKey, host_key_id)
        if item is None:
            raise SSHHostKeyError("HOST_KEY_NOT_FOUND", "Host key does not exist")
        item.status, item.trusted_at, item.trusted_by = "TRUSTED", datetime.utcnow(), user_id
        self.db.flush()
        return item

    def revoke(self, host_key_id: int) -> SSHHostKey:
        item = self.db.get(SSHHostKey, host_key_id)
        if item is None:
            raise SSHHostKeyError("HOST_KEY_NOT_FOUND", "Host key does not exist")
        item.status = "REVOKED"
        self.db.flush()
        return item
