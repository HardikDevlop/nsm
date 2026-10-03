from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


def utc_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)


class RemoteAccessCredential(Base):
    __tablename__ = "remote_access_credentials"
    __table_args__ = (
        UniqueConstraint("device_id", "protocol", name="uq_remote_access_credential_device_protocol"),
        CheckConstraint("protocol IN ('ssh', 'telnet')", name="ck_remote_access_credential_protocol"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="ck_remote_access_credential_port"),
        CheckConstraint("auth_type IN ('password', 'private_key')", name="ck_remote_access_credential_auth_type"),
        Index("ix_remote_access_credentials_device_id", "device_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    protocol: Mapped[str] = mapped_column(String(10), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(20), nullable=False, default="password")
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    device = relationship("Device", back_populates="remote_access_credentials")


class SSHHostKey(Base):
    __tablename__ = "ssh_host_keys"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'TRUSTED', 'REVOKED')", name="ck_ssh_host_key_status"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="ck_ssh_host_key_port"),
        UniqueConstraint("device_id", "port", name="uq_ssh_host_key_device_port"),
        Index("ix_ssh_host_keys_device_id", "device_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    key_type: Mapped[str] = mapped_column(String(64), nullable=False)
    public_host_key: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    trusted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trusted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    device = relationship("Device", back_populates="ssh_host_keys")


class RemoteAccessSession(Base):
    __tablename__ = "remote_access_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('connecting', 'connected', 'disconnected', 'failed', 'timeout')", name="ck_remote_access_session_status"),
        CheckConstraint("(status IN ('connecting', 'connected') AND ended_at IS NULL) OR (status NOT IN ('connecting', 'connected') AND ended_at IS NOT NULL)", name="ck_remote_access_session_terminal_state"),
        CheckConstraint("protocol IN ('ssh', 'telnet')", name="ck_remote_access_session_protocol"),
        Index("ix_remote_access_sessions_device_id", "device_id"),
        Index("ix_remote_access_sessions_user_id", "user_id"),
        Index("ix_remote_access_sessions_status", "status"),
        Index("ix_remote_access_sessions_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    credential_id: Mapped[int | None] = mapped_column(ForeignKey("remote_access_credentials.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    protocol: Mapped[str] = mapped_column(String(10), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    device_username: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="connecting")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disconnect_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
