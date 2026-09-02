# Flow Verification Report

Date: 2026-08-29
Scope: read-only audit of the current Flow module. No code or data was changed.

## Stage Matrix

| Stage | Status | Current evidence |
|---|---|---|
| Flow API analytics routes | PASS | backend/api/flow_routes.py registers talkers, sources, destinations, applications, protocols, conversations, interfaces, and trends under /api/v1/flows/analytics. |
| NetFlow v5 parser | PASS | backend/flow/parsers.py implements NetFlowParser._v5. |
| NetFlow v9 parser | PASS | backend/flow/parsers.py implements templates and NetFlowParser._v9. |
| IPFIX parser | PASS | IPFIXParser exists and reuses the template/data decoding path. |
| sFlow parser | PASS | SFlowParser implements sFlow v5 datagrams and flow samples. |
| J-Flow/NetStream compatibility | PARTIAL | CompatibleVendorFlowParser reuses NetFlow/IPFIX decoders only when wire-compatible; vendor-specific fields are not independently decoded. |
| Receiver/listener | NOT WIRED | No Flow UDP/TCP receiver or socket listener exists in backend/flow or the registered Flow routes. |
| UDP/TCP ports | NOT WIRED | No Flow receiver port is configured or opened by the current Flow module. |
| FastAPI startup integration | NOT WIRED | backend/main.py includes flow_router for analytics only; it does not instantiate/start a Flow receiver or FlowIngestService in lifespan. |
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

The missing production path is:

```text
exporter UDP/TCP packet
  -> Flow receiver/listener        MISSING
  -> protocol selection/parser     NOT REACHABLE
  -> FlowIngestService.submit()    NOT REACHABLE
  -> flow_records                  NO LIVE INGESTION PROOF
```

## Exact Missing Link

The current FastAPI application imports and registers flow_router, but only the analytics router is registered. There is no application-managed flow receiver startup task, no UDP/TCP socket binding, no exporter packet dispatch, and no code path connecting parsed NetFlow/sFlow/IPFIX payloads to FlowIngestService.submit().

Therefore:

- Exporters have no current application listener to send packets to.
- Parsers cannot receive production packets through the running FastAPI lifecycle.
- The writer is implemented but has no live receiver-to-parser caller.
- Analytics APIs and the frontend are read paths only.
- The Flow module is not currently receiving real NetFlow, sFlow, or IPFIX data based on current source.

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

