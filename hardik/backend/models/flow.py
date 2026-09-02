from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class FlowRecord(Base):
    """Append-oriented normalized NetFlow/IPFIX record."""

    __tablename__ = "flow_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exporter_ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    observation_domain: Mapped[str | None] = mapped_column(String(120))
    source_version: Mapped[str | None] = mapped_column(String(20))
    flow_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    flow_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    src_ip: Mapped[str | None] = mapped_column(String(64))
    dst_ip: Mapped[str | None] = mapped_column(String(64))
    src_port: Mapped[int | None] = mapped_column(Integer)
    dst_port: Mapped[int | None] = mapped_column(Integer)
    ip_protocol: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    packets: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    input_interface_id: Mapped[int | None] = mapped_column(Integer)
    output_interface_id: Mapped[int | None] = mapped_column(Integer)
    raw_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
