from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.session import Base
class SyslogRecord(Base):
    __tablename__ = 'syslog_records'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey('devices.id', ondelete='SET NULL'), nullable=True, index=True)
    interface_id: Mapped[int | None] = mapped_column(ForeignKey('interfaces.id', ondelete='SET NULL'), nullable=True, index=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey('alerts.id', ondelete='SET NULL'), nullable=True, index=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey('incidents.id', ondelete='SET NULL'), nullable=True, index=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), index=True)
    facility: Mapped[int | None] = mapped_column(Integer); severity: Mapped[int | None] = mapped_column(Integer, index=True)
    hostname: Mapped[str | None] = mapped_column(String(255), index=True); application: Mapped[str | None] = mapped_column(String(48), index=True)
    process_id: Mapped[str | None] = mapped_column(String(128)); message_id: Mapped[str | None] = mapped_column(String(32)); structured_data: Mapped[str | None] = mapped_column(Text)
    event_timestamp: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    message: Mapped[str] = mapped_column(Text); raw_message: Mapped[str] = mapped_column(Text); received_at: Mapped[datetime] = mapped_column(DateTime, index=True)
