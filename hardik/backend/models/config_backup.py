from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class DeviceConfigurationVersion(Base):
    __tablename__ = "device_configuration_versions"
    __table_args__ = (UniqueConstraint("device_id", "version", name="uq_device_config_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(40), index=True)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    encrypted_content: Mapped[str] = mapped_column(Text)
    is_startup: Mapped[bool] = mapped_column(Boolean, default=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    captured_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ConfigurationComparison(Base):
    __tablename__ = "configuration_comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    from_version: Mapped[int] = mapped_column(Integer)
    to_version: Mapped[int] = mapped_column(Integer)
    added_lines: Mapped[list] = mapped_column(JSON, default=list)
    removed_lines: Mapped[list] = mapped_column(JSON, default=list)
    changed_lines: Mapped[list] = mapped_column(JSON, default=list)
    initiated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
