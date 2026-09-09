from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .parsers import FlowParseError, IPFIXParser, SFlowParser
from .service import FlowIngestService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FlowReceiverStats:
    received_datagrams: int = 0
    parsed_records: int = 0
    submitted_records: int = 0
    dropped_records: int = 0
    malformed_datagrams: int = 0
    unsupported_datagrams: int = 0


class _FlowDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, receiver: "FlowReceiver", protocol: str):
        self.receiver = receiver
        self.protocol = protocol

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.receiver._transports.append(transport)

    def datagram_received(self, data: bytes, address: Any) -> None:
        exporter_ip = address[0] if isinstance(address, tuple) and address else "unknown"
        self.receiver.handle_datagram(self.protocol, data, exporter_ip)

    def error_received(self, exc: Exception) -> None:
        logger.warning("flow_receiver_socket_error protocol=%s error=%s", self.protocol, exc)


class FlowReceiver:
    """Application-managed UDP receiver for IPFIX and sFlow."""

    def __init__(
        self,
        ingest: FlowIngestService,
        bind_host: str = "0.0.0.0",
        ipfix_port: int = 4739,
        sflow_port: int = 6343,
    ):
        self.ingest = ingest
        self.bind_host = bind_host
        self.ipfix_port = ipfix_port
        self.sflow_port = sflow_port
        self.stats = FlowReceiverStats()
        self._transports: list[asyncio.BaseTransport] = []
        self._started = False
        self._ipfix_parser = IPFIXParser()
        self._sflow_parser = SFlowParser()

    async def start(self) -> None:
        if self._started:
            return
        try:
            loop = asyncio.get_running_loop()
            await loop.create_datagram_endpoint(
                lambda: _FlowDatagramProtocol(self, "ipfix"),
                local_addr=(self.bind_host, self.ipfix_port),
            )
            await loop.create_datagram_endpoint(
                lambda: _FlowDatagramProtocol(self, "sflow"),
                local_addr=(self.bind_host, self.sflow_port),
            )
        except Exception:
            await self.stop()
            raise
        self._started = True
        logger.info(
            "flow_receiver_started bind_host=%s ipfix_port=%s sflow_port=%s",
            self.bind_host,
            self.ipfix_port,
            self.sflow_port,
        )

    async def stop(self) -> None:
        for transport in self._transports:
            transport.close()
        self._transports.clear()
        self._started = False
        logger.info(
            "flow_receiver_stopped received=%s parsed=%s submitted=%s dropped=%s malformed=%s unsupported=%s persisted=%s",
            self.stats.received_datagrams,
            self.stats.parsed_records,
            self.stats.submitted_records,
            self.stats.dropped_records,
            self.stats.malformed_datagrams,
            self.stats.unsupported_datagrams,
            getattr(self.ingest, "persisted", 0),
        )

    def handle_datagram(self, listener_protocol: str, data: bytes, exporter_ip: str) -> None:
        self.stats.received_datagrams += 1
        try:
            protocol, parser = self._select_parser(listener_protocol, data)
            received_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if listener_protocol == "sflow":
                parsed = parser.parse_datagram(data, exporter_ip, received_at)
                records = parsed.flows
                counter_samples = parsed.counters
            else:
                records = parser.parse(data, exporter_ip, received_at)
                counter_samples = []
        except FlowParseError as exc:
            self.stats.malformed_datagrams += 1
            logger.warning(
                "flow_datagram_dropped reason=malformed protocol=%s exporter_ip=%s error=%s",
                listener_protocol,
                exporter_ip,
                exc,
            )
            return
        except ValueError as exc:
            self.stats.unsupported_datagrams += 1
            logger.warning(
                "flow_datagram_dropped reason=unsupported protocol=%s exporter_ip=%s error=%s",
                listener_protocol,
                exporter_ip,
                exc,
            )
            return
        except Exception:
            self.stats.malformed_datagrams += 1
            logger.exception(
                "flow_datagram_dropped reason=parser_error protocol=%s exporter_ip=%s",
                listener_protocol,
                exporter_ip,
            )
            return

        self.stats.parsed_records += len(records)
        if counter_samples:
            submit_counter = getattr(self.ingest, "submit_counter_nowait", None)
            if submit_counter is not None:
                for counter in counter_samples:
                    if submit_counter(counter) is False:
                        self.stats.dropped_records += 1
        for record in records:
            accepted = self.ingest.submit_nowait(record)
            if accepted is False:
                self.stats.dropped_records += 1
                logger.warning(
                    "flow_record_dropped reason=queue_full protocol=%s exporter_ip=%s",
                    protocol,
                    exporter_ip,
                )
            else:
                self.stats.submitted_records += 1
        logger.debug(
            "flow_datagram_processed protocol=%s exporter_ip=%s records=%s received=%s parsed=%s submitted=%s dropped=%s malformed=%s unsupported=%s persisted=%s",
            protocol,
            exporter_ip,
            len(records),
            self.stats.received_datagrams,
            self.stats.parsed_records,
            self.stats.submitted_records,
            self.stats.dropped_records,
            self.stats.malformed_datagrams,
            self.stats.unsupported_datagrams,
            getattr(self.ingest, "persisted", 0),
        )

    def _select_parser(self, listener_protocol: str, data: bytes):
        if listener_protocol == "sflow":
            return "sflow", self._sflow_parser
        if listener_protocol != "ipfix":
            raise ValueError(f"unsupported flow listener {listener_protocol}")
        if len(data) < 2:
            raise FlowParseError("flow packet is too short")
        version = int.from_bytes(data[:2], "big")
        if version == 10:
            return "ipfix", self._ipfix_parser
        raise ValueError(f"unsupported IPFIX version {version}")
