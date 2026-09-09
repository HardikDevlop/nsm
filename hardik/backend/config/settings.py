from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    backend_cors_origins: str = "http://localhost:3000,http://localhost:5173"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    alert_email_recipients: str = ""
    snmp_request_timeout: float = 3.0
    snmp_retries: int = 1
    snmp_operation_timeout: float = 120.0
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
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def allowed_themes(self) -> list[str]:
        return [theme.strip() for theme in self.branding_allowed_themes.split(",") if theme.strip() in {"light", "dark"}]


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
