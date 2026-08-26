"""Persistence models for Linux Server Monitoring.

These tables are independent from SNMP, ICMP, discovery, and polling data.
"""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


def linux_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)


class LinuxServer(Base):
    __tablename__ = "linux_servers"
    __table_args__ = (
        UniqueConstraint("ip_address", name="uq_linux_servers_ip_address"),
        Index("ix_linux_servers_site_status", "site_id", "status"),
        Index("ix_linux_servers_deleted_status", "deleted_at", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uuid: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid4()), unique=True, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True)
    hostname: Mapped[str] = mapped_column(String(160), index=True)
    ip_address: Mapped[str] = mapped_column(String(45), index=True)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    os_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    architecture: Mapped[str | None] = mapped_column(String(80), nullable=True)
    snmp_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    snmp_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    status: Mapped[str] = mapped_column(String(30), default="configured", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, onupdate=linux_now, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    credentials: Mapped[list["LinuxServerCredential"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )
    monitoring_config: Mapped["LinuxServerMonitoringConfig | None"] = relationship(
        back_populates="server", cascade="all, delete-orphan", uselist=False, single_parent=True
    )
    snmp_credential: Mapped["LinuxServerSNMPCredential | None"] = relationship(
        back_populates="server", cascade="all, delete-orphan", uselist=False, single_parent=True
    )
    metric_samples: Mapped[list["LinuxServerMetricSample"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )
    current_metric: Mapped["LinuxServerCurrentMetric | None"] = relationship(
        back_populates="server", cascade="all, delete-orphan", uselist=False, single_parent=True
    )
    interfaces: Mapped[list["LinuxServerInterface"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )
    disks: Mapped[list["LinuxServerDisk"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )
    security_events: Mapped[list["LinuxSecurityEvent"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )


class LinuxServerCredential(Base):
    __tablename__ = "linux_server_credentials"
    __table_args__ = (
        Index("ix_linux_server_credentials_server_enabled", "linux_server_id", "enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    linux_server_id: Mapped[int] = mapped_column(ForeignKey("linux_servers.id", ondelete="CASCADE"), index=True)
    auth_method: Mapped[str] = mapped_column(String(30), default="ssh_key")
    username: Mapped[str] = mapped_column(String(120))
    secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, onupdate=linux_now)

    server: Mapped[LinuxServer] = relationship(back_populates="credentials")


class LinuxServerSNMPCredential(Base):
    __tablename__ = "linux_server_snmp_credentials"
    __table_args__ = (UniqueConstraint("linux_server_id", name="uq_linux_server_snmp_credentials_server"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    linux_server_id: Mapped[int] = mapped_column(ForeignKey("linux_servers.id", ondelete="CASCADE"), index=True)
    username: Mapped[str] = mapped_column(String(120))
    auth_protocol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    encrypted_auth_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    privacy_protocol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    encrypted_privacy_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    security_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, onupdate=linux_now)

    server: Mapped[LinuxServer] = relationship(back_populates="snmp_credential")


class LinuxServerMonitoringConfig(Base):
    __tablename__ = "linux_server_monitoring_configs"
    __table_args__ = (
        UniqueConstraint("linux_server_id", name="uq_linux_server_monitoring_configs_server"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    linux_server_id: Mapped[int] = mapped_column(ForeignKey("linux_servers.id", ondelete="CASCADE"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    collect_cpu: Mapped[bool] = mapped_column(Boolean, default=True)
    collect_memory: Mapped[bool] = mapped_column(Boolean, default=True)
    collect_disk: Mapped[bool] = mapped_column(Boolean, default=True)
    collect_network: Mapped[bool] = mapped_column(Boolean, default=True)
    collect_processes: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=180)
    monitoring_status: Mapped[str] = mapped_column(String(20), default="stopped", index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, onupdate=linux_now)

    server: Mapped[LinuxServer] = relationship(back_populates="monitoring_config")


class LinuxServerMetricSample(Base):
    """Future persisted metric shape; no code currently writes samples."""

    __tablename__ = "linux_server_metric_samples"
    __table_args__ = (
        Index("ix_linux_server_metric_samples_server_collected", "linux_server_id", "collected_at"),
        Index("ix_linux_server_metric_samples_retention_collected", "collected_at", "id"),
        Index("ix_linux_server_metric_samples_server_status", "linux_server_id", "collection_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    linux_server_id: Mapped[int] = mapped_column(ForeignKey("linux_servers.id", ondelete="CASCADE"), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, index=True)
    collection_status: Mapped[str] = mapped_column(String(30), default="not_collected", index=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    swap_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_io_read_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_io_write_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_5m: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_15m: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_rx_bytes: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_tx_bytes: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_rx_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_tx_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    packets_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    interface_errors: Mapped[float | None] = mapped_column(Float, nullable=True)
    interface_drops: Mapped[float | None] = mapped_column(Float, nullable=True)
    process_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, index=True)

    server: Mapped[LinuxServer] = relationship(back_populates="metric_samples")


class LinuxServerCurrentMetric(Base):
    """One current snapshot per server; this row is never retention-cleaned."""

    __tablename__ = "linux_server_current_metrics"
    __table_args__ = (UniqueConstraint("linux_server_id", name="uq_linux_server_current_metrics_server"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    linux_server_id: Mapped[int] = mapped_column(ForeignKey("linux_servers.id", ondelete="CASCADE"), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, index=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    swap_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_io_read_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_io_write_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_5m: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_15m: Mapped[float | None] = mapped_column(Float, nullable=True)
    uptime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_rx_bytes: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_tx_bytes: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_rx_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_tx_bytes_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    packets_per_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    interface_errors: Mapped[float | None] = mapped_column(Float, nullable=True)
    interface_drops: Mapped[float | None] = mapped_column(Float, nullable=True)
    process_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    server: Mapped[LinuxServer] = relationship(back_populates="current_metric")


class LinuxServerInterface(Base):
    __tablename__ = "linux_server_interfaces"
    __table_args__ = (
        UniqueConstraint("linux_server_id", "interface_name", name="uq_linux_server_interfaces_server_name"),
        Index("ix_linux_server_interfaces_server_state", "linux_server_id", "state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    linux_server_id: Mapped[int] = mapped_column(ForeignKey("linux_servers.id", ondelete="CASCADE"), index=True)
    interface_name: Mapped[str] = mapped_column(String(160))
    mac_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_addresses: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    speed_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    mtu: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, onupdate=linux_now)

    server: Mapped[LinuxServer] = relationship(back_populates="interfaces")


class LinuxServerDisk(Base):
    __tablename__ = "linux_server_disks"
    __table_args__ = (
        UniqueConstraint("linux_server_id", "mount_point", name="uq_linux_server_disks_server_mount"),
        Index("ix_linux_server_disks_server_collected", "linux_server_id", "collected_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    linux_server_id: Mapped[int] = mapped_column(ForeignKey("linux_servers.id", ondelete="CASCADE"), index=True)
    device: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mount_point: Mapped[str] = mapped_column(String(255))
    filesystem: Mapped[str | None] = mapped_column(String(120), nullable=True)
    total_bytes: Mapped[float | None] = mapped_column(Float, nullable=True)
    used_bytes: Mapped[float | None] = mapped_column(Float, nullable=True)
    available_bytes: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, onupdate=linux_now)

    server: Mapped[LinuxServer] = relationship(back_populates="disks")


class LinuxSecurityEvent(Base):
    __tablename__ = "linux_security_events"
    __table_args__ = (
        UniqueConstraint("linux_server_id", "event_hash", name="uq_linux_security_events_server_hash"),
        Index("ix_linux_security_events_server_timestamp", "linux_server_id", "event_timestamp"),
        Index("ix_linux_security_events_retention_timestamp", "event_timestamp", "id"),
        Index("ix_linux_security_events_server_type_severity", "linux_server_id", "event_type", "severity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    linux_server_id: Mapped[int] = mapped_column(ForeignKey("linux_servers.id", ondelete="CASCADE"), index=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    destination_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    destination_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    raw_message: Mapped[str] = mapped_column(Text)
    event_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=linux_now, index=True)

    server: Mapped[LinuxServer] = relationship(back_populates="security_events")


LINUX_MONITORING_TABLES = (
    LinuxServer.__table__,
    LinuxServerCredential.__table__,
    LinuxServerSNMPCredential.__table__,
    LinuxServerMonitoringConfig.__table__,
    LinuxServerMetricSample.__table__,
    LinuxServerCurrentMetric.__table__,
    LinuxServerInterface.__table__,
    LinuxServerDisk.__table__,
    LinuxSecurityEvent.__table__,
)
