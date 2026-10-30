"""Minimal password-based Windows credential API contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class WindowsCredentialCreate(BaseModel):
    device_id: int = Field(gt=0)
    auth_method: Literal["password"] = "password"
    username: str = Field(min_length=1, max_length=120)
    domain: str | None = Field(default=None, max_length=160)
    connection_host: str | None = Field(default=None, min_length=1, max_length=255)
    secret: SecretStr = Field(min_length=1)
    enabled: bool = True


class WindowsCredentialUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=120)
    domain: str | None = Field(default=None, max_length=160)
    connection_host: str | None = Field(default=None, min_length=1, max_length=255)
    secret: SecretStr | None = Field(default=None, min_length=1)
    enabled: bool | None = None


class WindowsCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    auth_method: Literal["password"]
    username: str
    domain: str | None = None
    connection_host: str | None = None
    enabled: bool
    is_verified: bool
    last_verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WindowsCredentialPersisted(BaseModel):
    """Internal service-layer handoff after encryption; never an API response."""

    model_config = ConfigDict(extra="forbid")

    device_id: int = Field(gt=0)
    auth_method: Literal["password"] = "password"
    username: str = Field(min_length=1, max_length=120)
    domain: str | None = Field(default=None, max_length=160)
    encrypted_secret: str = Field(min_length=1)
    enabled: bool = True

    @model_validator(mode="after")
    def reject_plaintext_field(self):
        if "secret" in self.model_fields_set:
            raise ValueError("Persisted credentials must contain encrypted_secret only")
        return self


class WindowsThresholdConfigBase(BaseModel):
    """Validated threshold values shared by Windows threshold requests."""

    cpu_threshold: float = Field(default=40, ge=1, le=100)
    memory_threshold: float = Field(default=40, ge=1, le=100)
    disk_threshold: float = Field(default=40, ge=1, le=100)
    enabled: bool = True


class WindowsThresholdConfigCreate(WindowsThresholdConfigBase):
    device_id: int = Field(gt=0)


class WindowsThresholdConfigUpdate(BaseModel):
    cpu_threshold: float | None = Field(default=None, ge=1, le=100)
    memory_threshold: float | None = Field(default=None, ge=1, le=100)
    disk_threshold: float | None = Field(default=None, ge=1, le=100)
    enabled: bool | None = None


class WindowsThresholdConfigRead(WindowsThresholdConfigBase):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    device_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WindowsThresholdNotificationStateRead(BaseModel):
    """Read-only contract for independent Windows threshold state."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    metric_name: Literal["cpu", "memory", "disk"]
    state: Literal["normal", "warning"]
    last_value: float | None = None
    threshold_at_transition: float | None = None
    last_transition_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class WindowsHardwareSnapshotRead(BaseModel):
    """Public, non-sensitive latest Windows hardware snapshot."""

    model_config = ConfigDict(from_attributes=True)

    device_id: int
    collected_at: datetime | None
    computer_system: dict
    system_product: dict
    baseboard: dict
    bios: dict
    processors: list[dict]
    memory_modules: list[dict]
    memory_arrays: list[dict]


class WindowsUSBInventoryRead(BaseModel):
    """Read-only, non-persistent USB inventory response."""

    device_id: int
    collected_at: str
    status: str
    usb: dict
