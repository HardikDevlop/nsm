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
    authority_level: int = 0
    is_assignable: bool = True


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    role_name: str | None = None
    authority_level: int | None = None
    is_assignable: bool | None = None


class RoleRead(RoleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_system_role: bool


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
    status: Literal["active", "disabled", "suspended"] = "active"


class UserCreate(UserBase):
    password: str = Field(min_length=6)


class UserUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=6)
    role_id: int | None = None
    max_concurrent_sessions: int | None = Field(default=None, ge=1, le=10)


class UserStatusUpdate(BaseModel):
    status: Literal["active", "disabled", "suspended"]
    suspended_until: datetime | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    name: str
    email: EmailStr
    role_id: int | None = None
    role_name: str | None = None
    authority_level: int = 0
    permissions: list[str] = []
    status: str
    created_at: datetime
    max_concurrent_sessions: int = 1


class UserSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    session_id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revoke_reason: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    active: bool = False


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
    outcome: str = "success"
    timestamp: datetime


class DeviceStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    old_status: str | None = None
    new_status: str
    change_reason: str | None = None
    timestamp: datetime


class GeneratedReportRead(BaseModel):
    id: int
    schedule_id: int | None = None
    report_name: str
    format: str
    status: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    file_size: int | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class ReportScheduleBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    enabled: bool = False
    frequency: Literal["daily", "weekly", "monthly"]
    run_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str | None = None
    report_format: Literal["csv"] = "csv"
    filters: dict = Field(default_factory=dict)


class ReportScheduleCreate(ReportScheduleBase):
    pass


class ReportScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    enabled: bool | None = None
    frequency: Literal["daily", "weekly", "monthly"] | None = None
    run_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str | None = None
    report_format: Literal["csv"] | None = None
    filters: dict | None = None


class ReportScheduleRead(ReportScheduleBase):
    id: int
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None

    model_config = {"from_attributes": True}


class ReportManagementFilters(BaseModel):
    device_type_id: int | None = None
    device_id: int | None = None
    site_id: int | None = None
    device_status: Literal["all", "up", "down", "unreachable"] = "all"
    alert_severity: Literal["all", "critical", "high", "medium", "low", "warning", "info"] = "all"
    protocol: Literal["all", "snmp", "icmp"] = "all"
    period: Literal["today", "yesterday", "weekly", "monthly", "yearly", "custom"] = "today"
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


class ReportInterfaceDetail(BaseModel):
    interface_id: int
    name: str | None = None
    admin_status: str | None = None
    operational_status: str | None = None
    speed: str | None = None
    avg_utilization_pct: float | None = None
    max_utilization_pct: float | None = None
    p95_utilization_pct: float | None = None
    avg_inbound_mbps: float | None = None
    avg_outbound_mbps: float | None = None
    avg_error_rate_pct: float | None = None
    current_status: str | None = None


class ReportInventory(BaseModel):
    hostname: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    device_type: str | None = None
    vendor: str | None = None
    model: str | None = None
    serial_number: str | None = None
    os_version: str | None = None
    firmware_version: str | None = None
    site: str | None = None
    snmp_version: str | None = None
    first_discovered_at: datetime | None = None
    last_seen_at: datetime | None = None


class ReportManagementRecord(BaseModel):
    device_id: int
    hostname: str
    ip_address: str
    site_name: str | None = None
    device_type_name: str | None = None
    protocol: str
    availability_pct: float | None = None
    downtime_seconds: int
    outage_count: int = 0
    longest_outage_seconds: int = 0
    last_outage_time: datetime | None = None
    last_recovery_time: datetime | None = None
    current_status: str
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
    max_cpu_percent: float | None = None
    p95_cpu_percent: float | None = None
    max_memory_percent: float | None = None
    p95_memory_percent: float | None = None
    max_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    avg_packet_loss_pct: float | None = None
    max_packet_loss_pct: float | None = None
    interface_details: list[ReportInterfaceDetail] = []
    interface_details_total: int = 0
    interface_details_truncated: bool = False
    alert_details: list["ReportAlertDetail"] = []
    alert_details_total: int = 0
    alert_details_truncated: bool = False
    inventory: ReportInventory
    alert_count: int = 0
    critical_alert_count: int = 0
    warning_alert_count: int = 0
    active_alert_count: int = 0
    resolved_alert_count: int = 0
    alert_mttr_seconds: float | None = None
    sla_target_percent: float | None = None
    sla_variance_percent: float | None = None
    allowed_downtime_seconds: int | None = None
    sla_breach_seconds: int | None = None
    sla_status: str
    period_start: datetime
    period_end: datetime


class ReportAlertDetail(BaseModel):
    alert_id: int
    device_id: int | None = None
    device_name: str | None = None
    site_name: str | None = None
    severity: str
    title: str
    description: str | None = None
    created_at: datetime | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by: int | None = None
    resolved_at: datetime | None = None
    duration_seconds: int | None = None
    status: str


class ReportManagementSection(BaseModel):
    title: str
    count: int
    average: float | None = None
    maximum: float | None = None
    minimum: float | None = None


class ReportTrendAvailabilityPoint(BaseModel):
    bucket: datetime
    availability_percent: float | None = None


class ReportTrendPerformancePoint(BaseModel):
    bucket: datetime
    cpu_avg: float | None = None
    memory_avg: float | None = None
    latency_avg_ms: float | None = None


class ReportTrendBandwidthPoint(BaseModel):
    bucket: datetime
    rx_mbps: float | None = None
    tx_mbps: float | None = None


class ReportTrendAlertPoint(BaseModel):
    bucket: datetime
    total: int
    critical: int
    warning: int
    info: int


class ReportManagementTrends(BaseModel):
    bucket_granularity: Literal["hourly", "daily", "monthly"]
    availability: list[ReportTrendAvailabilityPoint] = []
    performance: list[ReportTrendPerformancePoint] = []
    bandwidth: list[ReportTrendBandwidthPoint] = []
    alerts: list[ReportTrendAlertPoint] = []


class ReportManagementSummary(BaseModel):
    filters: ReportManagementFilters
    period_start: datetime
    period_end: datetime
    total_devices: int
    total_records: int
    availability_pct: float | None = None
    downtime_seconds: int
    avg_snmp_health: float | None = None
    avg_performance_score: float | None = None
    sla_met_pct: float
    sla_configured_devices: int
    sla_met_devices: int
    sla_breached_devices: int
    sla_unknown_devices: int
    snmp_devices: int
    icmp_devices: int
    up_devices: int
    down_devices: int
    unreachable_devices: int
    total_alerts: int
    critical_alerts: int
    total_outages: int
    warning_alerts: int
    info_alerts: int
    active_alerts: int
    resolved_alerts: int
    acknowledged_alerts: int
    alert_mttr_seconds: float | None = None
    most_affected_device_id: int | None = None
    most_affected_device_name: str | None = None
    alert_details: list[ReportAlertDetail] = []
    alert_details_total: int = 0
    alert_details_truncated: bool = False
    trends: ReportManagementTrends
    inventory_total_assets: int
    inventory_by_device_type: dict[str, int]
    inventory_by_vendor: dict[str, int]
    inventory_unknown_assets: int
    sections: dict[str, ReportManagementSection]
    records: list[ReportManagementRecord]


# ---------------------------------------------------------------- Dashboard / operations
class DashboardSummary(BaseModel):
    total_devices: int
    online_devices: int
    offline_devices: int
    health_counts: dict[str, int]
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
