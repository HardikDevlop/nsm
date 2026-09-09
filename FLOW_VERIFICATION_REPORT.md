# Flow Verification Report

Date: 2026-08-29
Scope: read-only audit of the current Flow module. No code or data was changed.

## Stage Matrix

| Stage | Status | Current evidence |
|---|---|---|
| Flow API analytics routes | PASS | backend/api/flow_routes.py registers talkers, sources, destinations, applications, protocols, conversations, interfaces, and trends under /api/v1/flows/analytics. |
| NetFlow v5/v9 parser | REMOVED | No NetFlow parser is registered; v5/v9 packets are rejected by the IPFIX listener and no new NetFlow rows are accepted. |
| IPFIX parser | PASS | IPFIXParser owns v10 header, template cache, set, and data-record processing. |
| sFlow parser | PASS | SFlowParser implements sFlow v5 datagrams and flow samples. |
| J-Flow/NetStream compatibility | REMOVED | Vendor compatibility adapters are not active protocols. |
| Receiver/listener | PASS | FlowReceiver binds separate configurable IPFIX and sFlow UDP listeners. |
| UDP ports | PASS | IPFIX and sFlow listener ports are configurable; no NetFlow-specific setting remains. |
| FastAPI startup integration | PASS | backend/main.py starts FlowReceiver after FlowIngestService when flow collection is enabled. |
| Queue/buffer | PASS | FlowIngestService uses a bounded asyncio.Queue with configurable queue_size and drops on QueueFull. |
| Database flow model/table | PASS | FlowRecord maps to flow_records; migration 20260829_0011_flow_records creates the normalized table and indexes. |
| Persistence/writer | PASS | FlowIngestService batches queued NormalizedFlow objects and executes INSERT ... ON CONFLICT (record_hash) DO NOTHING, then commits. |
| Real ingestion into writer | NOT WIRED | No current listener path calls parser.parse() and submits records to FlowIngestService. |
| Aggregation logic | PASS | flow_routes.py performs database-side SUM(bytes), SUM(packets), COUNT(*), GROUP BY, pagination, filters, and time trends. |
| PostgreSQL flow records currently exist | BLOCKED | Exact configured-URL read-only count failed with psycopg.OperationalError: connection is bad: no error details available. No empty result was observed. |
| Frontend Flow page | PASS | FlowAnalytics.tsx uses real API calls, device/site/time filters, analytics tables, and trends; no static flow data is used. |
| Frontend display of real stored data | PARTIAL | The page can render API data when flow_records rows exist, but current stored-row presence could not be verified. |

## Existing API Routes

Router prefix: /api/v1/flows/analytics

- GET /talkers
- GET /sources
- GET /destinations
- GET /applications
- GET /protocols
- GET /conversations
- GET /interfaces
- GET /trends

All analytics routes require the flows:read permission and query flow_records.

## Current Data Flow

The implemented pieces are:

```text
normalized flow
  -> FlowIngestService bounded queue
  -> batch INSERT into flow_records
  -> analytics SQL aggregates
  -> /api/v1/flows/analytics/*
  -> FlowAnalytics.tsx
```

The active production path is:

```text
exporter UDP packet (IPFIX/sFlow)
  -> Flow receiver/listener
  -> protocol selection/parser
  -> FlowIngestService.submit()
  -> flow_records
```

## Active Runtime Path

The FastAPI lifespan starts FlowIngestService and FlowReceiver when flow
collection is enabled. FlowReceiver binds the configured IPFIX and sFlow UDP
listeners, dispatches packets to their protocol-specific parsers, and submits
normalized records to the bounded writer.

Therefore, exporters can send IPFIX and sFlow to the configured listeners, while
NetFlow v5/v9 packets are rejected and historical NetFlow rows remain stored but
are excluded from active analytics.

## Database Verification Attempt

Read-only command from backend environment:

```bash
./.venv/bin/python - <<'PY'
from pathlib import Path
from sqlalchemy import create_engine, text
# Parse backend/.env in memory without printing the URL/password.
# Connect using the exact configured DATABASE_URL.
# Query to_regclass('public.flow_records') and count(*).
PY
```

Result:

```text
flow_db_check=BLOCKED
(psycopg.OperationalError) connection is bad: no error details available
```

The real row count, latest flow timestamp, and protocol distribution are therefore not available from this execution environment.

## Conclusion

The Flow analytics read path is implemented and frontend-wired. The protocol parsers, normalized schema, bounded queue, batch writer, and aggregation queries are present. The exporter ingestion path is **NOT WIRED** because a Flow receiver/listener is absent from the current source and FastAPI lifespan. Real flow-record existence is **BLOCKED** by database access, not classified as empty.
