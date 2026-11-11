"""Minimal password-based WinRM credential persistence model."""

from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from enum import Enum

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, JSON, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


def windows_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)


class WindowsCredential(Base):
    """Encrypted password credential associated directly with an existing Device."""

    __tablename__ = "windows_credentials"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_windows_credentials_device_id"),
        CheckConstraint("auth_method = 'password'", name="ck_windows_credentials_password_only"),
        Index("ix_windows_credentials_device_enabled", "device_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    auth_method: Mapped[str] = mapped_column(
        String(20), default="password", nullable=False
    )
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(160), nullable=True)
    connection_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=windows_now, onupdate=windows_now, nullable=False
    )

    device = relationship("Device")


class WindowsHelperCredential(Base):
    """One-time-issued, helper-only credential; plaintext is never persisted."""
    __tablename__ = "windows_helper_credentials"
    __table_args__ = (
        UniqueConstraint("token_prefix", name="uq_windows_helper_credentials_prefix"),
        Index("ix_windows_helper_credentials_device_active", "device_id", "is_active"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    device = relationship("Device")


class WindowsHelperSubmission(Base):
    """Durable idempotency/replay record with short-lived helper evidence."""
    __tablename__ = "windows_helper_submissions"
    __table_args__ = (UniqueConstraint("collection_id", name="uq_windows_helper_submission_collection"),
                      Index("ix_windows_helper_submission_expiry", "expires_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(Integer, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    device = relationship("Device")


class WindowsHelperChallenge(Base):
    """Durable, device-bound challenge state for helper collection binding."""
    __tablename__ = "windows_helper_challenges"
    __table_args__ = (
        UniqueConstraint("challenge_id", name="uq_windows_helper_challenges_id"),
        UniqueConstraint("device_id", "collection_id", name="uq_windows_helper_challenges_device_collection"),
        Index("ix_windows_helper_challenges_device_expiry", "device_id", "expires_at"),
        Index("ix_windows_helper_challenges_collection", "collection_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    challenge_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    collection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device = relationship("Device")


class WindowsThresholdConfig(Base):
    """Per-device UI threshold configuration for Windows monitoring."""

    __tablename__ = "windows_threshold_configs"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_windows_threshold_configs_device_id"),
        CheckConstraint(
            "cpu_threshold >= 1 AND cpu_threshold <= 100",
            name="ck_windows_threshold_configs_cpu_range",
        ),
        CheckConstraint(
            "memory_threshold >= 1 AND memory_threshold <= 100",
            name="ck_windows_threshold_configs_memory_range",
        ),
        CheckConstraint(
            "disk_threshold >= 1 AND disk_threshold <= 100",
            name="ck_windows_threshold_configs_disk_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cpu_threshold: Mapped[float] = mapped_column(Float, default=40, nullable=False)
    memory_threshold: Mapped[float] = mapped_column(Float, default=40, nullable=False)
    disk_threshold: Mapped[float] = mapped_column(Float, default=40, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=windows_now, onupdate=windows_now, nullable=False
    )

    device = relationship("Device")


class WindowsThresholdNotificationState(Base):
    """Device-scoped warning state; intentionally independent of global alerts."""

    __tablename__ = "windows_threshold_notification_states"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "metric_name",
            name="uq_windows_threshold_notification_states_device_metric",
        ),
        CheckConstraint(
            "metric_name IN ('cpu', 'memory', 'disk')",
            name="ck_windows_threshold_notification_states_metric",
        ),
        CheckConstraint(
            "state IN ('normal', 'warning')",
            name="ck_windows_threshold_notification_states_state",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(20), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    last_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_at_transition: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_transition_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=windows_now, onupdate=windows_now, nullable=False
    )

    device = relationship("Device")


class WindowsCABundleStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    INVALID = "invalid"


class WindowsCABundleTrustType(str, Enum):
    ENTERPRISE_CA = "enterprise_ca"
    SELF_SIGNED_EXPLICIT = "self_signed_explicit"


class WindowsCABundle(Base):
    """Metadata for a site-scoped CA bundle stored outside PostgreSQL."""

    __tablename__ = "windows_ca_bundles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked', 'expired', 'invalid')",
            name="ck_windows_ca_bundles_status",
        ),
        CheckConstraint(
            "trust_type IN ('enterprise_ca', 'self_signed_explicit')",
            name="ck_windows_ca_bundles_trust_type",
        ),
        UniqueConstraint("site_id", "sha256_fingerprint", name="uq_windows_ca_bundles_site_fingerprint"),
        Index("ix_windows_ca_bundles_site_status", "site_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    sha256_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    not_before: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    not_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_ca: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_self_signed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    trust_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=WindowsCABundleStatus.ACTIVE.value)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, onupdate=windows_now, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    site = relationship("Site")
    assignments = relationship("WindowsDeviceCAAssignment", back_populates="ca_bundle")


class WindowsDeviceCAAssignment(Base):
    """Versioned assignment; an active assignment has no unassigned timestamp."""

    __tablename__ = "windows_device_ca_assignments"
    __table_args__ = (
        Index(
            "uq_windows_device_ca_active",
            "device_id",
            unique=True,
            postgresql_where=text("unassigned_at IS NULL"),
        ),
        Index("ix_windows_device_ca_assignments_bundle", "ca_bundle_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    ca_bundle_id: Mapped[int] = mapped_column(ForeignKey("windows_ca_bundles.id", ondelete="RESTRICT"), nullable=False, index=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ca_bundle = relationship("WindowsCABundle", back_populates="assignments")
    device = relationship("Device")


WINDOWS_MONITORING_TABLES = (WindowsCredential.__table__,)

class WindowsSystemSnapshot(Base):
    __tablename__ = "windows_system_snapshots"
    __table_args__ = (UniqueConstraint("device_id", name="uq_windows_system_snapshots_device_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    system_info: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cpu: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    memory: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    disks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    device = relationship("Device")

WINDOWS_MONITORING_TABLES = (WindowsCredential.__table__, WindowsSystemSnapshot.__table__)

class WindowsMetricSnapshot(Base):
    __tablename__ = "windows_metric_snapshots"
    __table_args__ = (UniqueConstraint("device_id", "module", name="uq_windows_metric_snapshots_device_module"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(20), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    device = relationship("Device")


class WindowsProcessCollection(Base):
    """Durable lifecycle state for one device process collection."""
    __tablename__ = "windows_process_collections"
    __table_args__ = (
        UniqueConstraint("collection_id", name="uq_windows_process_collections_collection"),
        Index("ix_windows_process_collections_device_state", "device_id", "state"),
        Index("ix_windows_process_collections_expiry", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    collection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    device = relationship("Device")


class WindowsProcessSnapshot(Base):
    __tablename__ = "windows_process_snapshots"
    __table_args__ = (
        UniqueConstraint("collection_id", name="uq_windows_process_snapshots_collection_id"),
        Index("ix_windows_process_snapshots_device_collected", "device_id", "collected_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collection_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True)
    process_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    device = relationship("Device")
    items = relationship("WindowsProcessSnapshotItem", back_populates="snapshot", cascade="all, delete-orphan", passive_deletes=True)


class WindowsProcessSnapshotItem(Base):
    __tablename__ = "windows_process_snapshot_items"
    __table_args__ = (
        Index("ix_windows_process_snapshot_items_snapshot", "snapshot_id"),
        Index("ix_windows_process_snapshot_items_device_identity", "device_id", "process_id", "process_creation_time"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("windows_process_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    process_id: Mapped[int] = mapped_column(Integer, nullable=False)
    process_creation_time: Mapped[str | None] = mapped_column(String(80), nullable=True)
    process_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parent_process_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cpu_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    working_set_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    private_memory_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    thread_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(80), nullable=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification_confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    application_group_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snapshot = relationship("WindowsProcessSnapshot", back_populates="items")
    device = relationship("Device")

class WindowsMetricHistory(Base):
    """Append-only Windows collection history; current snapshots remain separate."""
    __tablename__ = "windows_metric_history"
    __table_args__ = (Index("ix_windows_metric_history_device_module_time", "device_id", "module", "collected_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(40), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    device = relationship("Device")


class WindowsHardwareSnapshot(Base):
    __tablename__ = "windows_hardware_snapshots"
    __table_args__ = (UniqueConstraint("device_id", name="uq_windows_hardware_snapshots_device_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    computer_system: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    system_product: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    baseboard: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    bios: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    processors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    memory_modules: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    memory_arrays: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    device = relationship("Device")

class WindowsEventLog(Base):
    __tablename__ = "windows_event_logs"
    __table_args__ = (
        UniqueConstraint("device_id", "channel", "record_id", name="uq_windows_event_logs_device_channel_record"),
        Index("ix_windows_event_logs_device_id", "device_id"),
        Index("ix_windows_event_logs_channel", "channel"),
        Index("ix_windows_event_logs_time_created", "time_created"),
        Index("ix_windows_event_logs_event_id", "event_id"),
        Index("ix_windows_event_logs_level", "level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    channel: Mapped[str] = mapped_column(String(120), nullable=False)
    record_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    time_created: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    level: Mapped[str | None] = mapped_column(String(80), nullable=True)
    machine_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=windows_now, nullable=False)
    device = relationship("Device")

WINDOWS_MONITORING_TABLES = (
    WindowsCredential.__table__,
    WindowsHelperCredential.__table__,
    WindowsHelperSubmission.__table__,
    WindowsHelperChallenge.__table__,
    WindowsSystemSnapshot.__table__,
    WindowsMetricSnapshot.__table__,
    WindowsProcessSnapshot.__table__,
    WindowsProcessSnapshotItem.__table__,
    WindowsProcessCollection.__table__,
    WindowsHardwareSnapshot.__table__,
    WindowsEventLog.__table__,
)
