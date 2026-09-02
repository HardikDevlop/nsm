from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.session import Base
class SyslogCorrelationRule(Base):
    __tablename__='syslog_correlation_rules'
    id:Mapped[int]=mapped_column(Integer,primary_key=True,index=True); name:Mapped[str]=mapped_column(String(160),unique=True); pattern:Mapped[str]=mapped_column(String(500)); min_severity:Mapped[int|None]=mapped_column(Integer,nullable=True); alert_severity:Mapped[str]=mapped_column(String(30),default='warning'); cooldown_seconds:Mapped[int]=mapped_column(Integer,default=300); enabled:Mapped[bool]=mapped_column(Boolean,default=True); created_by:Mapped[int|None]=mapped_column(ForeignKey('users.id',ondelete='SET NULL'),nullable=True); created_at:Mapped[datetime]=mapped_column(DateTime)
