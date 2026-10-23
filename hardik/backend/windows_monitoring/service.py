"""Credential lifecycle operations for the isolated Windows foundation."""

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import Device
from backend.config.settings import get_settings
from backend.utils.crypto import decrypt_secret, encrypt_secret

from .models import WindowsCredential
from .schemas import WindowsCredentialCreate, WindowsCredentialRead, WindowsCredentialUpdate
from .winrm import WinRMConnectionDiagnostic, WinRMHTTPSAdapter


class WindowsCredentialService:
    """Persist encrypted Windows passwords and test them through WinRM HTTPS."""

    @staticmethod
    def _device(db: Session, device_id: int) -> Device:
        device = db.query(Device).filter(Device.id == device_id).first()
        if device is None:
            raise ValueError("device does not exist")
        return device

    @staticmethod
    def _read(credential: WindowsCredential) -> WindowsCredentialRead:
        return WindowsCredentialRead.model_validate(credential)

    def create(self, db: Session, payload: WindowsCredentialCreate) -> WindowsCredentialRead:
        self._device(db, payload.device_id)
        if payload.connection_host:
            WinRMHTTPSAdapter._validate_target(payload.connection_host, 5986)
        credential = WindowsCredential(
            device_id=payload.device_id,
            auth_method="password",
            username=payload.username,
            domain=payload.domain,
            connection_host=payload.connection_host,
            encrypted_secret=encrypt_secret(payload.secret.get_secret_value()),
            enabled=payload.enabled,
        )
        db.add(credential)
        db.flush()
        return self._read(credential)

    def retrieve(self, db: Session, credential_id: int) -> WindowsCredentialRead:
        credential = db.query(WindowsCredential).filter(WindowsCredential.id == credential_id).first()
        if credential is None:
            raise ValueError("Windows credential does not exist")
        return self._read(credential)

    def update(
        self, db: Session, credential_id: int, payload: WindowsCredentialUpdate
    ) -> WindowsCredentialRead:
        credential = db.query(WindowsCredential).filter(WindowsCredential.id == credential_id).first()
        if credential is None:
            raise ValueError("Windows credential does not exist")
        values = payload.model_dump(exclude_unset=True)
        if values.get("connection_host"):
            WinRMHTTPSAdapter._validate_target(values["connection_host"], 5986)
        secret = values.pop("secret", None)
        if secret is not None:
            credential.encrypted_secret = encrypt_secret(secret.get_secret_value())
            credential.is_verified = False
            credential.last_verified_at = None
        for field, value in values.items():
            setattr(credential, field, value)
        db.flush()
        return self._read(credential)

    def delete(self, db: Session, credential_id: int) -> None:
        credential = db.query(WindowsCredential).filter(WindowsCredential.id == credential_id).first()
        if credential is None:
            raise ValueError("Windows credential does not exist")
        db.delete(credential)
        db.flush()

    def test_connection(
        self,
        db: Session,
        credential_id: int,
        *,
        port: int = 5986,
        ca_trust_path: str | None = None,
        connect_timeout: int = 30,
        operation_timeout: int = 20,
        adapter_factory=WinRMHTTPSAdapter,
    ) -> WinRMConnectionDiagnostic:
        credential = db.query(WindowsCredential).filter(WindowsCredential.id == credential_id).first()
        if credential is None:
            raise ValueError("Windows credential does not exist")
        if not credential.enabled:
            return WinRMConnectionDiagnostic(False, "authentication", "Windows credential is disabled")
        password = decrypt_secret(credential.encrypted_secret)
        if not password:
            return WinRMConnectionDiagnostic(False, "protocol", "Windows credential is unavailable")
        configured_ca_path = ca_trust_path or get_settings().windows_ca_trust_path
        if not configured_ca_path:
            return WinRMConnectionDiagnostic(False, "tls", "Windows CA trust is not configured")
        trust_path = Path(configured_ca_path)
        if not trust_path.is_file() or not trust_path.stat().st_size:
            return WinRMConnectionDiagnostic(False, "tls", "Windows CA trust configuration is invalid")
        device = self._device(db, credential.device_id)
        username = f"{credential.domain}\\{credential.username}" if credential.domain else credential.username
        diagnostic = adapter_factory(
            getattr(credential, "connection_host", None) or device.hostname or device.ip_address,
            username,
            password,
            port=port,
            ca_trust_path=str(trust_path),
            connect_timeout=connect_timeout,
            operation_timeout=operation_timeout,
        ).test_connection()
        if diagnostic.ok:
            credential.is_verified = True
            credential.last_verified_at = datetime.now().replace(microsecond=0)
        else:
            credential.is_verified = False
        db.flush()
        return diagnostic
