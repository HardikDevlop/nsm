from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from .models import NormalizedFlow

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


class FlowIngestService:
    """Bounded queue and batch writer; it never holds DB sessions while parsing."""

    def __init__(self, db_factory, queue_size: int = 10_000, batch_size: int = 500, flush_seconds: float = 1.0):
        self.db_factory, self.batch_size, self.flush_seconds = db_factory, batch_size, flush_seconds
        self.queue: asyncio.Queue[NormalizedFlow] = asyncio.Queue(maxsize=queue_size)
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
                    db.execute(INSERT_FLOW, [flow_values(flow) for flow in batch])
                    db.commit()
                self.persisted += len(batch)
                logger.info("flow_records_persisted count=%s total=%s", len(batch), self.persisted)
            finally:
                for _ in batch:
                    self.queue.task_done()
