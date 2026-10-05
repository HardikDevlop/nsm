from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RemoteAccessCredentialCreate(BaseModel):
    device_id: int = Field(gt=0)
    protocol: Literal["ssh", "telnet"]
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)
    auth_type: Literal["password", "private_key"] = "password"
    secret: str = Field(min_length=1)


class RemoteAccessCredentialUpdate(BaseModel):
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=120)
    auth_type: Literal["password", "private_key"] | None = None
    secret: str | None = Field(default=None, min_length=1)


class RemoteAccessCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: int
    protocol: Literal["ssh", "telnet"]
    port: int
    username: str
    auth_type: Literal["password", "private_key"]
    is_verified: bool
    last_verified_at: datetime | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class RemoteAccessSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_uuid: str
    device_id: int
    credential_id: int | None
    user_id: int
    protocol: Literal["ssh", "telnet"]
    port: int
    device_username: str
    status: Literal["connecting", "connected", "disconnected", "failed", "timeout"]
    started_at: datetime
    last_activity_at: datetime
    ended_at: datetime | None
    disconnect_reason: str | None
    source_ip: str | None
    created_at: datetime


class RemoteAccessSessionCreate(BaseModel):
    device_id: int = Field(gt=0)
    protocol: Literal["ssh", "telnet"]
    port: int | None = Field(default=None, ge=1, le=65535)
    credential_id: int | None = Field(default=None, gt=0)
    username: str | None = Field(default=None, min_length=1, max_length=120)
    secret: str | None = Field(default=None, min_length=1)
    remember_credential: bool = False

    @model_validator(mode="after")
    def credential_source(self):
        if self.credential_id is None and (self.username is None or self.secret is None):
            raise ValueError("credential_id or temporary username and secret is required")
        if self.credential_id is not None and (self.username is not None or self.secret is not None):
            raise ValueError("choose a saved credential or temporary credentials")
        return self


class RemoteAccessTestRequest(BaseModel):
    device_id: int = Field(gt=0)
    protocol: Literal["ssh", "telnet"]
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)
    secret: str = Field(min_length=1)
    auth_type: Literal["password", "private_key"] = "password"
    remember_credential: bool = False


class SSHHostKeyScanRequest(BaseModel):
    device_id: int = Field(gt=0)
    port: int = Field(default=22, ge=1, le=65535)


class SSHHostKeyTrustRequest(BaseModel):
    host_key_id: int = Field(gt=0)


class SSHHostKeyRead(BaseModel):
    id: int
    device_id: int
    host: str
    port: int
    key_type: str
    fingerprint: str
    status: Literal["PENDING", "TRUSTED", "REVOKED"]
