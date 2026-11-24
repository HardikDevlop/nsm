from functools import lru_cache
from pathlib import Path
import base64
import binascii
import re

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_CHALLENGE_KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NMS Backend"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://postgres:123456@localhost:5432/postgres"
    secret_key: str = "change-this-secret-key"
    access_token_expire_minutes: int = 1440
    credential_encryption_key: str = ""
    # Optional future helper-challenge signing keys. Format:
    # ``key_id=base64url(raw-key-bytes),previous_id=base64url(raw-key-bytes)``.
    # Empty values disable challenge signing. The active ID selects the issuer;
    # other configured IDs are verification-only during key rotation.
    windows_helper_challenge_keys: str = ""
    windows_helper_challenge_active_key_id: str = ""
    # Server-side trust anchor for Windows WinRM HTTPS; never supplied by API callers.
    windows_ca_trust_path: str = ""
    # Private root for uploaded Windows CA bundle files; empty means fail closed.
    windows_ca_storage_root: str = ""
    backend_cors_origins: str = "http://localhost:3000,http://localhost:5173"
    trusted_proxy_ips: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    alert_email_recipients: str = ""
    report_email_enabled: bool = False
    report_email_recipients: str = ""
    report_email_hour: int = 11
    report_email_minute: int = 0
    report_timezone: str = "Asia/Kolkata"
    snmp_request_timeout: float = 3.0
    snmp_retries: int = 1
    snmp_operation_timeout: float = 120.0
    snmp_raw_cache_ttl_seconds: float = 10.0
    snmp_raw_cache_max_entries: int = 2048
    snmp_root_concurrency: int = 3
    windows_task_manager_collection_capacity: int = 2
    windows_process_history_retention_days: int = 7
    windows_memory_poll_interval_seconds: int = 180
    windows_memory_polling_enabled: bool = False
    # Proposal-only safety switch. No SNMP cleanup job runs while this is 0.
    snmp_history_retention_days: int = 0
    redis_url: str = "redis://localhost:6379/0"
    redis_cache_ttl_seconds: int = 10
    flow_enabled: bool = False
    flow_bind_host: str = "0.0.0.0"
    flow_ipfix_port: int = 4739
    flow_sflow_port: int = 6343
    syslog_enabled: bool = False
    syslog_bind_host: str = "0.0.0.0"
    syslog_udp_port: int = 5514
    syslog_tcp_port: int = 6514
    syslog_enable_udp: bool = True
    syslog_enable_tcp: bool = True
    syslog_retention_days: int = 0
    branding_application_name: str = "NMS"
    branding_logo_url: str = ""
    branding_allowed_themes: str = "light,dark"

    @property
    def trusted_proxies(self) -> set[str]:
        return {item.strip() for item in self.trusted_proxy_ips.split(",") if item.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def allowed_themes(self) -> list[str]:
        return [theme.strip() for theme in self.branding_allowed_themes.split(",") if theme.strip() in {"light", "dark"}]

    @staticmethod
    def _decode_challenge_keys(value: str) -> dict[str, bytes]:
        keys: dict[str, bytes] = {}
        for entry in value.split(","):
            entry = entry.strip()
            if not entry or entry.count("=") != 1:
                raise ValueError("WINDOWS_HELPER_CHALLENGE_KEYS contains a malformed entry")
            key_id, encoded = (part.strip() for part in entry.split("=", 1))
            if not _CHALLENGE_KEY_ID.fullmatch(key_id):
                raise ValueError("WINDOWS_HELPER_CHALLENGE_KEYS contains an invalid key ID")
            if key_id in keys:
                raise ValueError("WINDOWS_HELPER_CHALLENGE_KEYS contains duplicate key IDs")
            if not encoded:
                raise ValueError("WINDOWS_HELPER_CHALLENGE_KEYS contains empty key material")
            try:
                padded = encoded + "=" * (-len(encoded) % 4)
                material = base64.urlsafe_b64decode(padded.encode("ascii"))
            except (UnicodeEncodeError, ValueError, binascii.Error) as exc:
                raise ValueError("WINDOWS_HELPER_CHALLENGE_KEYS contains invalid key material") from exc
            if len(material) < 32:
                raise ValueError("WINDOWS_HELPER_CHALLENGE_KEYS requires at least 32 decoded bytes per key")
            keys[key_id] = material
        return keys

    @model_validator(mode="after")
    def validate_helper_challenge_configuration(self):
        configured = self.windows_helper_challenge_keys.strip()
        active = self.windows_helper_challenge_active_key_id.strip()
        if not configured:
            if active:
                raise ValueError("WINDOWS_HELPER_CHALLENGE_ACTIVE_KEY_ID requires configured challenge keys")
            return self
        keys = self._decode_challenge_keys(configured)
        if not active:
            raise ValueError("WINDOWS_HELPER_CHALLENGE_ACTIVE_KEY_ID is required when challenge keys are configured")
        if active not in keys:
            raise ValueError("WINDOWS_HELPER_CHALLENGE_ACTIVE_KEY_ID does not identify a configured key")
        return self

    @property
    def windows_helper_challenge_key_map(self) -> dict[str, bytes]:
        """Decoded challenge keys for a future signer/verifier; never serialize them."""
        if not self.windows_helper_challenge_keys.strip():
            return {}
        return self._decode_challenge_keys(self.windows_helper_challenge_keys.strip())

    @property
    def windows_helper_challenge_active_key(self) -> bytes | None:
        return self.windows_helper_challenge_key_map.get(self.windows_helper_challenge_active_key_id.strip())


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.environment.lower() == "production":
        weak_secret = settings.secret_key in {
            "change-this-secret-key",
            "CHANGE_ME",
            "CHANGE_ME_TO_A_LONG_RANDOM_SECRET",
        } or len(settings.secret_key) < 32
        if weak_secret:
            raise ValueError(
                "Production requires SECRET_KEY with at least 32 non-placeholder characters"
            )
        if not settings.credential_encryption_key or settings.credential_encryption_key in {
            "CHANGE_ME",
            "CHANGE_ME_TO_A_LONG_RANDOM_SECRET",
        }:
            raise ValueError(
                "Production requires CREDENTIAL_ENCRYPTION_KEY for stored device credentials"
            )
    return settings
