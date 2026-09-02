from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class APMApplication(Base):
    __tablename__ = "apm_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    environment: Mapped[str] = mapped_column(String(80), nullable=False, default="production")
    owner: Mapped[str | None] = mapped_column(String(160))
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class APMService(Base):
    __tablename__ = "apm_services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("apm_applications.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    service_key: Mapped[str] = mapped_column(String(240), nullable=False)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    runtime: Mapped[str | None] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class APMTransaction(Base):
    __tablename__ = "apm_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("apm_services.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    operation_type: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class APMMetricSample(Base):
    """Aggregated application metric sample; raw request bodies are never stored."""

    __tablename__ = "apm_metric_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("apm_applications.id", ondelete="CASCADE"), nullable=False)
    service_id: Mapped[int] = mapped_column(ForeignKey("apm_services.id", ondelete="CASCADE"), nullable=False)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("apm_transactions.id", ondelete="SET NULL"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    response_time_ms: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    slow_transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    availability_percent: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("100"))
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class APMDependency(Base):
    __tablename__ = "apm_dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_service_id: Mapped[int] = mapped_column(ForeignKey("apm_services.id", ondelete="CASCADE"), nullable=False)
    target_service_id: Mapped[int | None] = mapped_column(ForeignKey("apm_services.id", ondelete="SET NULL"))
    target_name: Mapped[str] = mapped_column(String(240), nullable=False)
    dependency_type: Mapped[str | None] = mapped_column(String(60))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    response_time_ms: Mapped[float] = mapped_column(Float, nullable=False, server_default=text("0"))
