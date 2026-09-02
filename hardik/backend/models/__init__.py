import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base
from backend.models.flow import FlowRecord  # noqa: F401
from backend.models.apm import APMApplication, APMService, APMTransaction, APMMetricSample, APMDependency  # noqa: F401
from backend.models.rca import RCAIncident, RCAEvidence  # noqa: F401
from backend.models.incident import Incident, IncidentAlert, IncidentComment, IncidentAttachment, IncidentHistory, IncidentSLAConfig, IncidentSLATimer, IncidentSLAHistory  # noqa: F401
from backend.models.problem import Problem, ProblemIncident, ProblemHistory  # noqa: F401
from backend.models.change import ChangeRequest, ChangeCI, ChangeIncident, ChangeHistory  # noqa: F401
from backend.models.knowledge import KnowledgeArticle, KnowledgeArticleVersion, KnowledgeIncidentLink, KnowledgeProblemLink, KnowledgeDeviceLink, KnowledgeServiceLink  # noqa: F401
from backend.models.config_backup import DeviceConfigurationVersion, ConfigurationComparison  # noqa: F401
from backend.models.config_compliance import ConfigurationCompliancePolicy, ConfigurationComplianceViolation  # noqa: F401
from backend.models.availability import AvailabilityOutage, AvailabilityReport  # noqa: F401
from backend.models.virtualization import VirtualObject  # noqa: F401
from backend.models.qos import QoSSample  # noqa: F401
from backend.models.bgp import BGPObservation  # noqa: F401
from backend.models.syslog import SyslogRecord  # noqa: F401
from backend.models.syslog_rule import SyslogCorrelationRule  # noqa: F401


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


def utc_now() -> datetime:
    # PostgreSQL TIMESTAMP columns are naive; store application timestamps in IST.
    return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    role_name: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    users: Mapped[list["User"]] = relationship(back_populates="role")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
    )


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    module: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions,
        back_populates="permissions",
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uuid: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    role: Mapped[Role | None] = relationship(back_populates="users")
    alerts_acknowledged: Mapped[list["Alert"]] = relationship(back_populates="acknowledged_user")
    reports: Mapped[list["Report"]] = relationship(back_populates="generated_user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    sites: Mapped[list["Site"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160), index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    organization: Mapped[Organization] = relationship(back_populates="sites")
    devices: Mapped[list["Device"]] = relationship(back_populates="site")


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    vendor_name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    devices: Mapped[list["Device"]] = relationship(back_populates="vendor")


class DeviceType(Base):
    __tablename__ = "device_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    devices: Mapped[list["Device"]] = relationship(back_populates="device_type")
    thresholds: Mapped[list["Threshold"]] = relationship(back_populates="device_type")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    hostname: Mapped[str] = mapped_column(String(160), index=True)
    ip_address: Mapped[str] = mapped_column(String(45), unique=True, index=True)
    mac_address: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    device_type_id: Mapped[int | None] = mapped_column(ForeignKey("device_types.id"), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="unknown")
    monitoring_status: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    uptime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    downtime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    last_status_change: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    topology_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    site: Mapped[Site | None] = relationship(back_populates="devices")
    vendor: Mapped[Vendor | None] = relationship(back_populates="devices")
    device_type: Mapped[DeviceType | None] = relationship(back_populates="devices")
    credentials: Mapped[list["DeviceCredential"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    interfaces: Mapped[list["Interface"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    metrics: Mapped[list["DeviceMetric"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    monitoring_jobs: Mapped[list["MonitoringJob"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    status_history: Mapped[list["DeviceStatusHistory"]] = relationship(back_populates="device", cascade="all, delete-orphan")


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    snmp_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    community_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_protocol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    auth_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    privacy_protocol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    privacy_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    security_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ssh_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped[Device] = relationship(back_populates="credentials")


class Interface(Base):
    __tablename__ = "interfaces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    interface_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="unknown")
    speed: Mapped[str | None] = mapped_column(String(50), nullable=True)
    traffic_in: Mapped[float] = mapped_column(Float, default=0)
    traffic_out: Mapped[float] = mapped_column(Float, default=0)
    packet_errors: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    device: Mapped[Device] = relationship(back_populates="interfaces")


class MonitoringJob(Base):
    __tablename__ = "monitoring_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    monitor_type: Mapped[str] = mapped_column(String(80))
    interval: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(30), default="active")

    device: Mapped[Device] = relationship(back_populates="monitoring_jobs")


class DeviceMetric(Base):
    __tablename__ = "device_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    cpu_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency: Mapped[float | None] = mapped_column(Float, nullable=True)
    packet_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    bandwidth_usage: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    device: Mapped[Device] = relationship(back_populates="metrics")


class Threshold(Base):
    __tablename__ = "thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_type_id: Mapped[int | None] = mapped_column(ForeignKey("device_types.id"), nullable=True)
    metric_name: Mapped[str] = mapped_column(String(80), index=True)
    warning_value: Mapped[float] = mapped_column(Float)
    critical_value: Mapped[float] = mapped_column(Float)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    device_type: Mapped[DeviceType | None] = relationship(back_populates="thresholds")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    severity: Mapped[str] = mapped_column(String(30), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    device: Mapped[Device | None] = relationship(back_populates="alerts")
    acknowledged_user: Mapped[User | None] = relationship(back_populates="alerts_acknowledged")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="alert", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    device: Mapped[Device | None] = relationship(back_populates="events")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(60))
    sent_to: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    alert: Mapped[Alert | None] = relationship(back_populates="notifications")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    report_name: Mapped[str] = mapped_column(String(160))
    report_type: Mapped[str] = mapped_column(String(80), index=True)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    generated_user: Mapped[User | None] = relationship(back_populates="reports")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120))
    resource_name: Mapped[str] = mapped_column(String(160))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped[User | None] = relationship(back_populates="audit_logs")


class DeviceStatusHistory(Base):
    __tablename__ = "device_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30))
    change_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    device: Mapped[Device] = relationship(back_populates="status_history")


# Register normalized SNMP tables with Base.metadata without changing the
# existing device/discovery models or their public API.
from backend.models.snmp import (  # noqa: E402,F401
    Alarm, CPUStatistic, DeviceInterface, DeviceInventory, DevicePerformance, EnvironmentStatistic,
    InterfaceStatistic, LLDPNeighbor, MemoryStatistic, OIDCache, POEStatistic,
    PollingHistory, PowerStatistic, RoutingEntry, SNMPCredential, SNMPTrap,
    StorageStatistic, SystemHealth, VLANInformation, VendorProfile,
    MonitoringConfig, MonitoringField, MonitoringStatus, PollStatus,
    LatestCPU, LatestMemory, LatestStorage, LatestInterface, LatestEnvironment,
)
# Register new identity / capability / OUI / product catalog tables.
from backend.models.identity import (  # noqa: E402,F401
    DeviceCapabilities, DeviceIdentity, DeviceProduct, VendorOUI,
)
from backend.models.manual_topology import (  # noqa: E402,F401
    ManualTopologyChange, ManualTopologySnapshot,
)
from backend.models.cmdb import CIType, ConfigurationItem, CIRelationship, CIHistory  # noqa: E402,F401
