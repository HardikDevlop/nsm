from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class FlowRecord(Base):
    """Append-oriented normalized sFlow/IPFIX record."""

    __tablename__ = "flow_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exporter_ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    protocol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    observation_domain: Mapped[str | None] = mapped_column(String(120))
    source_version: Mapped[str | None] = mapped_column(String(20))
    flow_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    flow_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class SFlowCounterSample(Base):
    """Persisted sFlow generic interface counter observation."""

    __tablename__ = "sflow_counter_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    device_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    exporter_ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_address: Mapped[str] = mapped_column(String(64), nullable=False)
    sub_agent_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_index: Mapped[int] = mapped_column(Integer, nullable=False)
    interface_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    if_type: Mapped[int] = mapped_column(Integer, nullable=False)
    if_speed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_direction: Mapped[int] = mapped_column(Integer, nullable=False)
    if_status: Mapped[int] = mapped_column(Integer, nullable=False)
    if_in_octets: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_in_ucast_pkts: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_in_multicast_pkts: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_in_broadcast_pkts: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_in_discards: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_in_errors: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_out_octets: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_out_ucast_pkts: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_out_multicast_pkts: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_out_broadcast_pkts: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_out_discards: Mapped[int] = mapped_column(BigInteger, nullable=False)
    if_out_errors: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    raw_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
