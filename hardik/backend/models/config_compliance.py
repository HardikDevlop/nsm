from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.session import Base

class ConfigurationCompliancePolicy(Base):
    __tablename__ = "configuration_compliance_policies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)

class ConfigurationComplianceViolation(Base):
    __tablename__ = "configuration_compliance_violations"
    __table_args__ = (UniqueConstraint("policy_id", "device_id", "version", name="uq_config_compliance_violation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("configuration_compliance_policies.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
