from __future__ import annotations

import asyncio
import logging
import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from .models import NormalizedFlow
from .parsers import SFlowCounterSample
from .correlation import FlowCorrelationResolver

logger = logging.getLogger(__name__)


INSERT_FLOW = text("""
    INSERT INTO flow_records
      (device_id, exporter_ip, protocol, observation_domain, source_version, flow_start,
       flow_end, received_at, src_ip, dst_ip, src_port, dst_port, ip_protocol,
       bytes, packets, input_interface_id, output_interface_id, raw_fields,
       record_hash)
    VALUES (:device_id, :exporter_ip, :protocol, :observation_domain, :source_version,
      :flow_start, :flow_end, :received_at, :src_ip, :dst_ip, :src_port,
      :dst_port, :ip_protocol, :bytes, :packets, :input_interface_id,
      :output_interface_id, :raw_fields, :record_hash)
    ON CONFLICT (record_hash) DO NOTHING
""")

INSERT_SFLOW_COUNTER = text("""
    INSERT INTO sflow_counter_samples
      (device_id, exporter_ip, agent_address, sub_agent_id, sequence_number,
       if_index, interface_name, if_type, if_speed, if_direction, if_status,
       if_in_octets, if_in_ucast_pkts, if_in_multicast_pkts, if_in_broadcast_pkts,
       if_in_discards, if_in_errors, if_out_octets, if_out_ucast_pkts,
       if_out_multicast_pkts, if_out_broadcast_pkts, if_out_discards, if_out_errors,
       observed_at, raw_fields, record_hash)
    VALUES (:device_id, :exporter_ip, :agent_address, :sub_agent_id, :sequence_number,
       :if_index, :interface_name, :if_type, :if_speed, :if_direction, :if_status,
       :if_in_octets, :if_in_ucast_pkts, :if_in_multicast_pkts, :if_in_broadcast_pkts,
       :if_in_discards, :if_in_errors, :if_out_octets, :if_out_ucast_pkts,
       :if_out_multicast_pkts, :if_out_broadcast_pkts, :if_out_discards, :if_out_errors,
       :observed_at, :raw_fields, :record_hash)
    ON CONFLICT (record_hash) DO NOTHING
""")


def flow_values(flow: NormalizedFlow) -> dict[str, Any]:
    flow.validate()
    return {"device_id": flow.device_id, "exporter_ip": flow.exporter_ip, "protocol": flow.protocol,
            "observation_domain": flow.observation_domain, "source_version": flow.source_version,
            "flow_start": flow.flow_start, "flow_end": flow.flow_end, "received_at": flow.received_at,
            "src_ip": flow.src_ip, "dst_ip": flow.dst_ip, "src_port": flow.src_port,
            "dst_port": flow.dst_port, "ip_protocol": flow.ip_protocol, "bytes": flow.bytes,
            "packets": flow.packets, "input_interface_id": flow.input_interface_id,
            "output_interface_id": flow.output_interface_id, "raw_fields": flow.raw_fields,
            "record_hash": flow.record_hash}


def counter_values(counter: SFlowCounterSample) -> dict[str, Any]:
    identity = "|".join(str(value) for value in (
        counter.exporter_ip, counter.agent_address, counter.sub_agent_id,
        counter.sequence_number, counter.if_index, counter.observed_at.isoformat(),
    ))
    return {"device_id": counter.device_id, "exporter_ip": counter.exporter_ip,
            "agent_address": counter.agent_address, "sub_agent_id": counter.sub_agent_id,
            "sequence_number": counter.sequence_number, "if_index": counter.if_index,
            "interface_name": counter.interface_name, "if_type": counter.if_type,
            "if_speed": counter.if_speed, "if_direction": counter.if_direction,
            "if_status": counter.if_status, "if_in_octets": counter.if_in_octets,
            "if_in_ucast_pkts": counter.if_in_ucast_pkts,
            "if_in_multicast_pkts": counter.if_in_multicast_pkts,
            "if_in_broadcast_pkts": counter.if_in_broadcast_pkts,
            "if_in_discards": counter.if_in_discards, "if_in_errors": counter.if_in_errors,
            "if_out_octets": counter.if_out_octets, "if_out_ucast_pkts": counter.if_out_ucast_pkts,
            "if_out_multicast_pkts": counter.if_out_multicast_pkts,
            "if_out_broadcast_pkts": counter.if_out_broadcast_pkts,
            "if_out_discards": counter.if_out_discards, "if_out_errors": counter.if_out_errors,
            "observed_at": counter.observed_at, "raw_fields": counter.raw_fields,
            "record_hash": hashlib.sha256(identity.encode("utf-8")).hexdigest()}


class FlowIngestService:
    """Bounded queue and batch writer; it never holds DB sessions while parsing."""

    def __init__(self, db_factory, queue_size: int = 10_000, batch_size: int = 500, flush_seconds: float = 1.0, correlation: FlowCorrelationResolver | None = None):
        self.db_factory, self.batch_size, self.flush_seconds = db_factory, batch_size, flush_seconds
        self.correlation = correlation or FlowCorrelationResolver()
        self.queue: asyncio.Queue[NormalizedFlow | SFlowCounterSample] = asyncio.Queue(maxsize=queue_size)
        self._worker: asyncio.Task | None = None
        self.persisted = self.dropped = 0

    async def start(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        if self._worker:
            await self.queue.join()
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def submit(self, flow: NormalizedFlow) -> bool:
        return self.submit_nowait(flow)

    def submit_counter_nowait(self, counter: SFlowCounterSample) -> bool:
        try:
            self.queue.put_nowait(counter)
            return True
        except asyncio.QueueFull:
            self.dropped += 1
            return False

    def submit_nowait(self, flow: NormalizedFlow) -> bool:
        try:
            self.queue.put_nowait(flow)
            return True
        except asyncio.QueueFull:
            self.dropped += 1
            return False

    async def _consume(self) -> None:
        while True:
            first = await self.queue.get()
            batch = [first]
            deadline = asyncio.get_running_loop().time() + self.flush_seconds
            while len(batch) < self.batch_size:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    batch.append(await asyncio.wait_for(self.queue.get(), remaining))
                except asyncio.TimeoutError:
                    break
            try:
                with self.db_factory() as db:
                    flows = [item for item in batch if isinstance(item, NormalizedFlow)]
                    counters = [item for item in batch if isinstance(item, SFlowCounterSample)]
                    if flows:
                        self.correlation.correlate(db, flows)
                        db.execute(INSERT_FLOW, [flow_values(flow) for flow in flows])
                    if counters:
                        self.correlation.correlate_counters(db, counters)
                        db.execute(INSERT_SFLOW_COUNTER, [counter_values(counter) for counter in counters])
                    db.commit()
                self.persisted += len(batch)
                logger.info("flow_records_persisted count=%s total=%s", len(batch), self.persisted)
            finally:
                for _ in batch:
                    self.queue.task_done()
