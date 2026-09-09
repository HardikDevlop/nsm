from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Literal


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class BrandingRead(BaseModel):
    application_name: str
    logo_url: str | None = None
    allowed_themes: list[str]


# ---------------------------------------------------------------- Roles / RBAC
class RoleBase(BaseModel):
    role_name: str


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    role_name: str | None = None


class RoleRead(RoleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class PermissionBase(BaseModel):
    code: str
    name: str
    module: str
    action: str
    description: str | None = None


class PermissionCreate(PermissionBase):
    pass


class PermissionUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    module: str | None = None
    action: str | None = None
    description: str | None = None


class PermissionRead(PermissionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class RoleWithPermissions(RoleRead):
    permissions: list[PermissionRead] = []


class PermissionIds(BaseModel):
    permission_ids: list[int]


class AssignRoleRequest(BaseModel):
    role_id: int


# ---------------------------------------------------------------- Users
class UserBase(BaseModel):
    name: str
    email: EmailStr
    role_id: int | None = None
    status: str = "active"


class UserCreate(UserBase):
    password: str = Field(min_length=6)


class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=6)
    role_id: int | None = None
    status: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    name: str
    email: EmailStr
    role_id: int | None = None
    role_name: str | None = None
    permissions: list[str] = []
    status: str
    created_at: datetime


# ---------------------------------------------------------------- Organizations
class OrganizationBase(BaseModel):
    name: str
    description: str | None = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class OrganizationRead(OrganizationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ---------------------------------------------------------------- Sites
class SiteBase(BaseModel):
    organization_id: int
    name: str
    city: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class SiteCreate(SiteBase):
    pass


class SiteUpdate(BaseModel):
    organization_id: int | None = None
    name: str | None = None
    city: str | None = None
    state: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class SiteRead(SiteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------------------------------------------------------------- Vendors
class VendorBase(BaseModel):
    vendor_name: str


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    vendor_name: str | None = None


class VendorRead(VendorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------------------------------------------------------------- Device types
class DeviceTypeBase(BaseModel):
    name: str
    description: str | None = None


class DeviceTypeCreate(DeviceTypeBase):
    pass


class DeviceTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class DeviceTypeRead(DeviceTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ---------------------------------------------------------------- Devices
class DeviceBase(BaseModel):
    site_id: int | None = None
    hostname: str
    ip_address: str
    mac_address: str | None = None
    vendor_id: int | None = None
    device_type_id: int | None = None
    serial_number: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    status: str = "unknown"
    monitoring_status: bool = True
    topology_metadata: dict | None = None


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    site_id: int | None = None
    hostname: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    vendor_id: int | None = None
    device_type_id: int | None = None
    serial_number: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    status: str | None = None
    monitoring_status: bool | None = None
    vendor_name: str | None = None
    topology_metadata: dict | None = None


class DeviceRead(DeviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_seen: datetime | None = None
    created_at: datetime
    uptime_seconds: int
    downtime_seconds: int
    last_status_change: datetime | None = None
    vendor_name: str | None = None
    device_type: str | None = None
    snmp_version: str | None = None


class DeviceOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hostname: str
    ip_address: str
    mac_address: str | None = None
    model: str | None = None
    vendor_name: str | None = None
    device_type: str | None = None
    status: str


# ---------------------------------------------------------------- Device credentials
class DeviceCredentialBase(BaseModel):
    device_id: int
    snmp_version: str | None = None
    community_string: str | None = None
    username: str | None = None
    password: str | None = None
    auth_protocol: str | None = None
    auth_password: str | None = None
    privacy_protocol: str | None = None
    privacy_password: str | None = None
    security_level: str | None = None
    ssh_port: int | None = None
    api_token: str | None = None


class DeviceCredentialCreate(DeviceCredentialBase):
    pass


class DeviceCredentialUpdate(BaseModel):
    snmp_version: str | None = None
    community_string: str | None = None
    username: str | None = None
    password: str | None = None
    auth_protocol: str | None = None
    auth_password: str | None = None
    privacy_protocol: str | None = None
    privacy_password: str | None = None
    security_level: str | None = None
    ssh_port: int | None = None
    api_token: str | None = None


class DeviceCredentialRead(DeviceCredentialBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------------------------------------------------------------- Interfaces
class InterfaceBase(BaseModel):
    device_id: int
    interface_name: str
    status: str = "unknown"
    speed: str | None = None
    traffic_in: float = 0
    traffic_out: float = 0
    packet_errors: int = 0


class InterfaceCreate(InterfaceBase):
    pass


class InterfaceUpdate(BaseModel):
    interface_name: str | None = None
    status: str | None = None
    speed: str | None = None
    traffic_in: float | None = None
    traffic_out: float | None = None
    packet_errors: int | None = None


class InterfaceRead(InterfaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_updated: datetime


# ---------------------------------------------------------------- Monitoring jobs
class MonitoringJobBase(BaseModel):
    device_id: int
    monitor_type: str
    interval: int = 60
    status: str = "active"


class MonitoringJobCreate(MonitoringJobBase):
    pass


class MonitoringJobUpdate(BaseModel):
    monitor_type: str | None = None
    interval: int | None = None
    status: str | None = None


class MonitoringJobRead(MonitoringJobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------------------------------------------------------------- Device metrics
class DeviceMetricBase(BaseModel):
    device_id: int
    cpu_usage: float | None = None
    memory_usage: float | None = None
    disk_usage: float | None = None
    temperature: float | None = None
    latency: float | None = None
    packet_loss: float | None = None
    bandwidth_usage: float | None = None


class DeviceMetricCreate(DeviceMetricBase):
    pass


class DeviceMetricUpdate(BaseModel):
    cpu_usage: float | None = None
    memory_usage: float | None = None
    disk_usage: float | None = None
    temperature: float | None = None
    latency: float | None = None
    packet_loss: float | None = None
    bandwidth_usage: float | None = None


class DeviceMetricRead(DeviceMetricBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ---------------------------------------------------------------- Thresholds
class ThresholdBase(BaseModel):
    device_type_id: int | None = None
    metric_name: str
    warning_value: float
    critical_value: float


class ThresholdCreate(ThresholdBase):
    pass


class ThresholdUpdate(BaseModel):
    device_type_id: int | None = None
    metric_name: str | None = None
    warning_value: float | None = None
    critical_value: float | None = None


class ThresholdRead(ThresholdBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


# ---------------------------------------------------------------- Alerts
class AlertBase(BaseModel):
    device_id: int | None = None
    interface_id: int | None = None
    severity: str
    title: str
    description: str | None = None
    status: str = "open"


class AlertCreate(AlertBase):
    pass


class AlertUpdate(BaseModel):
    severity: str | None = None
    title: str | None = None
    description: str | None = None
    status: str | None = None


class AlertRead(AlertBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    acknowledged_by: int | None = None
    resolved_at: datetime | None = None
    created_at: datetime


# ---------------------------------------------------------------- Events
class EventBase(BaseModel):
    device_id: int | None = None
    event_type: str
    description: str | None = None


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    event_type: str | None = None
    description: str | None = None


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime


# ---------------------------------------------------------------- Notifications
class NotificationBase(BaseModel):
    alert_id: int | None = None
    channel: str
    sent_to: str
    status: str = "pending"


class NotificationCreate(NotificationBase):
    pass


class NotificationUpdate(BaseModel):
    channel: str | None = None
    sent_to: str | None = None
    status: str | None = None
    sent_at: datetime | None = None


class NotificationRead(NotificationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sent_at: datetime | None = None


# ---------------------------------------------------------------- Reports
class ReportBase(BaseModel):
    report_name: str
    report_type: str
    generated_by: int | None = None
    file_path: str | None = None


class ReportCreate(ReportBase):
    pass


class ReportUpdate(BaseModel):
    report_name: str | None = None
    report_type: str | None = None
    file_path: str | None = None


class ReportRead(ReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    generated_at: datetime


# ---------------------------------------------------------------- Audit / history
class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    user_name: str | None = None
    action: str
    resource_name: str
    timestamp: datetime


class DeviceStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    old_status: str | None = None
    new_status: str
    change_reason: str | None = None
    timestamp: datetime


class ReportManagementFilters(BaseModel):
    device_type_id: int | None = None
    device_id: int | None = None
    site_id: int | None = None
    protocol: Literal["all", "snmp", "icmp"] = "all"
    period: Literal["weekly", "monthly", "yearly", "custom"] = "weekly"
    start_date: datetime | None = None
    end_date: datetime | None = None


class ReportManagementOptionsItem(BaseModel):
    id: int
    name: str


class ReportManagementDeviceOption(BaseModel):
    id: int
    hostname: str
    ip_address: str
    device_type_id: int | None = None
    site_id: int | None = None
    status: str


class ReportManagementRecord(BaseModel):
    device_id: int
    hostname: str
    ip_address: str
    site_name: str | None = None
    device_type_name: str | None = None
    protocol: str
    availability_pct: float
    downtime_seconds: int
    snmp_success_rate: float | None = None
    icmp_success_rate: float | None = None
    snmp_health: str
    performance_score: float | None = None
    interface_count: int | None = None
    interface_down_count: int | None = None
    avg_cpu_percent: float | None = None
    avg_memory_percent: float | None = None
    avg_latency_ms: float | None = None
    packet_loss_pct: float | None = None
    sla_status: str
    period_start: datetime
    period_end: datetime


class ReportManagementSection(BaseModel):
    title: str
    count: int
    average: float | None = None
    maximum: float | None = None
    minimum: float | None = None


class ReportManagementSummary(BaseModel):
    filters: ReportManagementFilters
    period_start: datetime
    period_end: datetime
    total_devices: int
    total_records: int
    availability_pct: float
    downtime_seconds: int
    avg_snmp_health: float | None = None
    avg_performance_score: float | None = None
    sla_met_pct: float
    snmp_devices: int
    icmp_devices: int
    sections: dict[str, ReportManagementSection]
    records: list[ReportManagementRecord]


# ---------------------------------------------------------------- Dashboard / operations
class DashboardSummary(BaseModel):
    total_devices: int
    online_devices: int
    offline_devices: int
    active_alerts: int
    critical_alerts: int
    recent_events: int


class DiscoveryRequest(BaseModel):
    network_range: str
    site_id: int | None = None
    ports: list[int] = [22, 80, 443, 161, 162, 8080, 8443]
    scan_icmp: bool = True
    scan_ports: bool = True
    scan_snmp: bool = False
    snmp_community: str = "public"
    timeout_ms: int = 700
    max_hosts: int = 254


class MonitoringRunRequest(BaseModel):
    ip_addresses: list[str] | None = None
    timeout_ms: int = 1000
