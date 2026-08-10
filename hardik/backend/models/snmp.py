"""Normalized SNMP persistence models.

Each table keeps time-series facts separate from the device identity. JSON
payloads are intentionally limited to vendor extensions; stable fields remain
typed and indexed for PostgreSQL queries.
"""

from datetime import datetime
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database.session import Base


def now() -> datetime:
    return datetime.utcnow()


class SNMPBase:
    """Common audit timestamps required by all SNMP tables."""
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True, comment="UTC creation time")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, comment="UTC last update time")


class DeviceInventory(SNMPBase, Base):
    """System identity and hardware inventory collected from an SNMP device."""
    __tablename__ = "device_inventory"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    serial_number: Mapped[str | None] = mapped_column(String(160), comment="Chassis serial number")
    model: Mapped[str | None] = mapped_column(String(160))
    firmware: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    device: Mapped["Device"] = relationship()


class SNMPCredential(SNMPBase, Base):
    """Encrypted SNMP credential metadata; secret values are never stored raw."""
    __tablename__ = "snmp_credentials"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(10), default="v2c")
    username: Mapped[str | None] = mapped_column(String(120))
    security_level: Mapped[str | None] = mapped_column(String(30))
    encrypted_secret: Mapped[str | None] = mapped_column(Text, comment="Encrypted community/auth material")
    device: Mapped["Device"] = relationship()


class SNMPRecord(SNMPBase, Base):
    """Base shape for normalized per-device metric records."""
    __abstract__ = True
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="supported", comment="supported or Not Supported")
    value_json: Mapped[dict] = mapped_column(JSON, default=dict, comment="Normalized extension values")


class DevicePerformance(SNMPRecord, Base):
    __tablename__ = "device_performance"
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    memory_percent: Mapped[float | None] = mapped_column(Float)


class CPUStatistic(SNMPRecord, Base):
    __tablename__ = "cpu_statistics"
    utilization_percent: Mapped[float | None] = mapped_column(Float)


class MemoryStatistic(SNMPRecord, Base):
    __tablename__ = "memory_statistics"
    used_bytes: Mapped[float | None] = mapped_column(Float)
    total_bytes: Mapped[float | None] = mapped_column(Float)
    utilization_percent: Mapped[float | None] = mapped_column(Float)


class StorageStatistic(SNMPRecord, Base):
    __tablename__ = "storage_statistics"
    mount_name: Mapped[str | None] = mapped_column(String(255))
    used_bytes: Mapped[float | None] = mapped_column(Float)
    total_bytes: Mapped[float | None] = mapped_column(Float)
    utilization_percent: Mapped[float | None] = mapped_column(Float)


class EnvironmentStatistic(SNMPRecord, Base):
    __tablename__ = "environment_statistics"
    sensor_name: Mapped[str | None] = mapped_column(String(160))
    temperature_celsius: Mapped[float | None] = mapped_column(Float)
    power_watts: Mapped[float | None] = mapped_column(Float)


class PowerStatistic(SNMPRecord, Base):
    __tablename__ = "power_statistics"
    watts: Mapped[float | None] = mapped_column(Float)


class POEStatistic(SNMPRecord, Base):
    __tablename__ = "poe_statistics"
    port_name: Mapped[str | None] = mapped_column(String(160))
    watts: Mapped[float | None] = mapped_column(Float)


class VLANInformation(SNMPRecord, Base):
    __tablename__ = "vlan_information"
    vlan_id: Mapped[int | None] = mapped_column(Integer)
    vlan_name: Mapped[str | None] = mapped_column(String(160))


class LLDPNeighbor(SNMPRecord, Base):
    __tablename__ = "lldp_neighbors"
    local_port: Mapped[str | None] = mapped_column(String(160))
    remote_device: Mapped[str | None] = mapped_column(String(255))
    remote_port: Mapped[str | None] = mapped_column(String(160))


class RoutingEntry(SNMPRecord, Base):
    __tablename__ = "routing_table"
    destination: Mapped[str | None] = mapped_column(String(64), index=True)
    next_hop: Mapped[str | None] = mapped_column(String(64))


class SystemHealth(SNMPRecord, Base):
    __tablename__ = "system_health"
    health: Mapped[str] = mapped_column(String(30), default="unknown")
    reason: Mapped[str | None] = mapped_column(Text)


class PollingHistory(SNMPBase, Base):
    """One auditable poll attempt, including duration and failure details."""
    __tablename__ = "polling_history"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    collector: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)


class InterfaceStatistic(SNMPBase, Base):
    """Raw and calculated interface counter sample."""
    __tablename__ = "interface_statistics"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    interface_id: Mapped[int] = mapped_column(ForeignKey("interfaces.id", ondelete="CASCADE"), index=True)
    rx_mbps: Mapped[float | None] = mapped_column(Float)
    tx_mbps: Mapped[float | None] = mapped_column(Float)
    utilization_percent: Mapped[float | None] = mapped_column(Float)
    error_rate: Mapped[float | None] = mapped_column(Float)
    packet_rate: Mapped[float | None] = mapped_column(Float)
    peak_mbps: Mapped[float | None] = mapped_column(Float)
    average_mbps: Mapped[float | None] = mapped_column(Float)
    percentile95_mbps: Mapped[float | None] = mapped_column(Float)
    rx_octets: Mapped[float | None] = mapped_column(Float)
    tx_octets: Mapped[float | None] = mapped_column(Float)


class SNMPTrap(SNMPBase, Base):
    """Persisted trap envelope for event correlation."""
    __tablename__ = "snmp_traps"
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    source_ip: Mapped[str] = mapped_column(String(45), index=True)
    trap_type: Mapped[str | None] = mapped_column(String(160))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class OIDCache(SNMPBase, Base):
    """Cached vendor/OID support result to avoid repeated failed lookups."""
    __tablename__ = "oid_cache"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    oid: Mapped[str] = mapped_column(String(255), index=True)
    supported: Mapped[bool] = mapped_column(default=False)
    label: Mapped[str | None] = mapped_column(String(160))
    __table_args__ = (UniqueConstraint("device_id", "oid", name="uq_oid_cache_device_oid"),)


class VendorProfile(SNMPBase, Base):
    """Vendor metadata and optional OID overrides."""
    __tablename__ = "vendor_profiles"
    vendor_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    oid_map: Mapped[dict] = mapped_column(JSON, default=dict)


class DeviceInterface(SNMPBase, Base):
    """Normalized SNMP interface identity table kept separate from legacy CRUD."""
    __tablename__ = "device_interfaces"
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    if_index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    speed_bps: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (UniqueConstraint("device_id", "if_index", name="uq_device_interfaces_device_index"),)


class Alarm(SNMPBase, Base):
    """Normalized SNMP alarm table; legacy alerts remain untouched."""
    __tablename__ = "alarms"
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    severity: Mapped[str] = mapped_column(String(30), index=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
