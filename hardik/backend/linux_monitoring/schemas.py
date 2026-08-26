"""API schemas for the isolated Linux Server Monitoring foundation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class LinuxServerBase(BaseModel):
    site_id: int | None = None
    hostname: str = Field(min_length=1, max_length=160)
    ip_address: str = Field(min_length=1, max_length=45)
    display_name: str | None = Field(default=None, max_length=160)
    os_name: str | None = Field(default=None, max_length=120)
    os_version: str | None = Field(default=None, max_length=120)
    architecture: str | None = Field(default=None, max_length=80)
    snmp_available: bool | None = None
    snmp_version: str | None = Field(default=None, max_length=20)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    status: str = Field(default="configured", pattern="^(configured|active|disabled|error)$")
    enabled: bool = True


class LinuxServerCreate(LinuxServerBase):
    pass


class LinuxServerUpdate(BaseModel):
    site_id: int | None = None
    hostname: str | None = Field(default=None, min_length=1, max_length=160)
    ip_address: str | None = Field(default=None, min_length=1, max_length=45)
    display_name: str | None = Field(default=None, max_length=160)
    os_name: str | None = Field(default=None, max_length=120)
    os_version: str | None = Field(default=None, max_length=120)
    architecture: str | None = Field(default=None, max_length=80)
    snmp_available: bool | None = None
    snmp_version: str | None = Field(default=None, max_length=20)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    status: str | None = Field(default=None, pattern="^(configured|active|disabled|error)$")
    enabled: bool | None = None


class LinuxServerRead(LinuxServerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uuid: str
    last_seen_at: datetime | None = None
    last_error: str | None = None
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime


class LinuxServerCredentialCreate(BaseModel):
    auth_method: str = Field(default="ssh_key", pattern="^(ssh_key|password|agent)$")
    username: str = Field(min_length=1, max_length=120)
    secret_ref: str | None = Field(default=None, max_length=255)
    enabled: bool = True


class LinuxServerCredentialUpdate(BaseModel):
    auth_method: str | None = Field(default=None, pattern="^(ssh_key|password|agent)$")
    username: str | None = Field(default=None, min_length=1, max_length=120)
    secret_ref: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None


class LinuxServerCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linux_server_id: int
    auth_method: str
    username: str
    secret_ref: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class LinuxServerMonitoringConfigUpdate(BaseModel):
    enabled: bool = False
    collect_cpu: bool = True
    collect_memory: bool = True
    collect_disk: bool = True
    collect_network: bool = True
    collect_processes: bool = False
    interval_seconds: int = Field(default=180, ge=180, le=180)


class LinuxServerMonitoringConfigRead(LinuxServerMonitoringConfigUpdate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linux_server_id: int
    created_at: datetime
    updated_at: datetime


class LinuxServerDetectRequest(BaseModel):
    ip_address: str = Field(min_length=1, max_length=45)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)
    auth_method: str = Field(default="ssh_key", pattern="^(ssh_key|password|agent)$")
    password: SecretStr | None = None
    private_key_path: str | None = Field(default=None, max_length=500)
    snmp_version: str = Field(default="v2c", pattern="^(v2c|v3)$")
    snmp_community: SecretStr | None = None
    snmp_username: str | None = Field(default=None, max_length=120)
    snmp_security_level: str = Field(default="authPriv", pattern="^authPriv$")
    snmp_auth_protocol: str = Field(default="sha", pattern="^(md5|sha)$")
    snmp_privacy_protocol: str = Field(default="aes", pattern="^(aes|aes128|des)$")
    snmp_auth_password: SecretStr | None = None
    snmp_privacy_password: SecretStr | None = None
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)

    @model_validator(mode="after")
    def validate_authentication(self):
        if self.auth_method == "password" and self.password is None:
            raise ValueError("SSH password is required for Password authentication")
        if self.auth_method == "ssh_key" and not self.private_key_path:
            raise ValueError("Private Key Path is required for Private Key authentication")
        if self.snmp_version == "v3" and not self.snmp_username:
            raise ValueError("SNMPv3 username is required")
        if self.snmp_version == "v3" and not self.snmp_auth_password:
            raise ValueError("SNMPv3 Auth Password is required")
        if self.snmp_version == "v3" and not self.snmp_privacy_password:
            raise ValueError("SNMPv3 Privacy Password is required")
        return self


class LinuxServerAddRequest(LinuxServerDetectRequest):
    site_id: int | None = None
    display_name: str | None = Field(default=None, max_length=160)


class LinuxServerSSHValidateRequest(BaseModel):
    ip_address: str = Field(min_length=1, max_length=45)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)
    auth_method: str = Field(default="password", pattern="^(ssh_key|password|agent)$")
    password: SecretStr | None = None
    private_key_path: str | None = Field(default=None, max_length=500)
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)

    @model_validator(mode="after")
    def validate_ssh_authentication(self):
        if self.auth_method == "password" and self.password is None:
            raise ValueError("SSH password is required for Password authentication")
        if self.auth_method == "ssh_key" and not self.private_key_path:
            raise ValueError("Private Key Path is required for Private Key authentication")
        return self


class LinuxServerSNMPValidateRequest(BaseModel):
    ip_address: str = Field(min_length=1, max_length=45)
    snmp_version: str = Field(default="v3", pattern="^v3$")
    snmp_username: str = Field(min_length=1, max_length=120)
    snmp_security_level: str = Field(default="authPriv", pattern="^authPriv$")
    snmp_auth_protocol: str = Field(default="sha", pattern="^(md5|sha)$")
    snmp_privacy_protocol: str = Field(default="aes", pattern="^(aes|aes128|des)$")
    snmp_auth_password: SecretStr
    snmp_privacy_password: SecretStr
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)


class LinuxServerInterfaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linux_server_id: int
    interface_name: str
    mac_address: str | None = None
    ip_addresses: list = []
    state: str | None = None
    speed_mbps: float | None = None
    mtu: int | None = None
    collected_at: datetime
    created_at: datetime
    updated_at: datetime


class LinuxServerDiskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linux_server_id: int
    device: str | None = None
    mount_point: str
    filesystem: str | None = None
    total_bytes: float | None = None
    used_bytes: float | None = None
    available_bytes: float | None = None
    usage_percent: float | None = None
    collected_at: datetime
    created_at: datetime
    updated_at: datetime


class LinuxServerDetectedInterface(BaseModel):
    interface_name: str
    mac_address: str | None = None
    ip_addresses: list = []
    state: str | None = None
    speed_mbps: float | None = None
    mtu: int | None = None


class LinuxServerDetectedDisk(BaseModel):
    device: str | None = None
    mount_point: str
    filesystem: str | None = None
    total_bytes: float | None = None
    used_bytes: float | None = None
    available_bytes: float | None = None
    usage_percent: float | None = None


class LinuxServerDetectedData(BaseModel):
    ip_address: str
    hostname: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    architecture: str | None = None
    snmp_available: bool | None = None
    snmp_version: str | None = None
    interfaces: list[LinuxServerDetectedInterface] = []
    disks: list[LinuxServerDetectedDisk] = []
    status: str = "active"
    ssh_valid: bool = False
    snmp_valid: bool = False
    ssh_error: str | None = None
    snmp_error: str | None = None


class LinuxServerDetectionResponse(BaseModel):
    success: bool
    status: str
    message: str
    data: LinuxServerDetectedData | None = None
    warnings: list[str] = []
    ssh_valid: bool = False
    snmp_valid: bool = False
    ssh_error: str | None = None
    snmp_error: str | None = None


class LinuxServerDetailsRead(LinuxServerRead):
    interfaces: list[LinuxServerInterfaceRead] = []
    disks: list[LinuxServerDiskRead] = []
    monitoring_config: LinuxServerMonitoringConfigRead | None = None


class LinuxServerMetricsCollectRequest(BaseModel):
    snmp_version: str = Field(default="v3", pattern="^v3$")
    username: str = Field(min_length=1, max_length=120)
    auth_protocol: str | None = Field(default=None, pattern="^(md5|sha)$")
    auth_password: SecretStr | None = None
    privacy_protocol: str | None = Field(default=None, pattern="^(aes|aes128|des)$")
    privacy_password: SecretStr | None = None
    security_level: str | None = Field(default=None, max_length=30)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=60.0)


class LinuxMonitoringStartRequest(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=120)
    auth_protocol: str | None = Field(default=None, pattern="^(md5|sha)$")
    auth_password: SecretStr | None = None
    privacy_protocol: str | None = Field(default=None, pattern="^(aes|aes128|des)$")
    privacy_password: SecretStr | None = None
    security_level: str | None = Field(default=None, max_length=30)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=60.0)


class LinuxMonitoringStatusRead(BaseModel):
    server_id: int
    enabled: bool
    status: str
    interval_seconds: int
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_started_at: datetime | None = None
    last_stopped_at: datetime | None = None
    last_error: str | None = None


class LinuxRetentionStatusRead(BaseModel):
    retention_hours: int = 24
    last_cleanup_at: datetime | None = None
    last_cleanup_error: str | None = None


class LinuxServerMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linux_server_id: int
    collected_at: datetime
    collection_status: str
    cpu_percent: float | None = None
    memory_percent: float | None = None
    swap_percent: float | None = None
    disk_percent: float | None = None
    disk_io_read_bytes_per_sec: float | None = None
    disk_io_write_bytes_per_sec: float | None = None
    load_1m: float | None = None
    load_5m: float | None = None
    load_15m: float | None = None
    uptime_seconds: float | None = None
    network_rx_bytes_per_sec: float | None = None
    network_tx_bytes_per_sec: float | None = None
    packets_per_sec: float | None = None
    interface_errors: float | None = None
    interface_drops: float | None = None
    details: dict = {}
    error_message: str | None = None
    created_at: datetime


class LinuxServerCurrentMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linux_server_id: int
    collected_at: datetime
    cpu_percent: float | None = None
    memory_percent: float | None = None
    swap_percent: float | None = None
    disk_percent: float | None = None
    disk_io_read_bytes_per_sec: float | None = None
    disk_io_write_bytes_per_sec: float | None = None
    load_1m: float | None = None
    load_5m: float | None = None
    load_15m: float | None = None
    uptime_seconds: float | None = None
    network_rx_bytes: float | None = None
    network_tx_bytes: float | None = None
    network_rx_bytes_per_sec: float | None = None
    network_tx_bytes_per_sec: float | None = None
    packets_per_sec: float | None = None
    interface_errors: float | None = None
    interface_drops: float | None = None
    process_count: int | None = None
    details: dict = {}


class LinuxServerMetricCollectionResponse(BaseModel):
    success: bool
    status: str
    message: str
    data: LinuxServerMetricRead | None = None


class LinuxSecurityCollectRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    auth_method: str = Field(default="ssh_key", pattern="^(ssh_key|password|agent)$")
    password: SecretStr | None = None
    private_key_path: str | None = Field(default=None, max_length=500)
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    lookback_minutes: int = Field(default=1440, ge=1, le=10080)
    max_events: int = Field(default=500, ge=1, le=5000)


class LinuxSecurityEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linux_server_id: int
    event_timestamp: datetime
    source_ip: str | None = None
    destination_ip: str | None = None
    destination_port: int | None = None
    event_type: str
    severity: str | None = None
    raw_message: str
    event_hash: str
    created_at: datetime


class LinuxSecurityCollectResponse(BaseModel):
    success: bool
    status: str
    message: str
    logs_available: bool
    collected_events: int
    duplicate_events: int
    warnings: list[str] = []
    events: list[LinuxSecurityEventRead] = []
