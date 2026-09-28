# Data retention and archival policy

The NMS keeps operational history in PostgreSQL and uses bounded cleanup jobs for tables that can grow continuously. Cleanup is disabled by default (`0` days) until an operator explicitly configures a retention period.

| Data | Configuration | Current behavior |
|---|---|---|
| SNMP/device history | `SNMP_HISTORY_RETENTION_DAYS` | Reserved safety switch; no automatic deletion when `0`. |
| Syslog records | `SYSLOG_RETENTION_DAYS` or the Syslog retention action | Bounded batch deletion by `received_at`; `0` means keep. |
| APM samples | `/apm/retention/run?retention_days=N` | Explicit, bounded cleanup by sample time. |
| Linux metric/security history | Linux scheduler retention settings | Automatic bounded cleanup using indexed timestamps. |
| Current/latest tables | Not applicable | Never retention-cleaned; they represent the latest state. |

Operational rules:

- Retention is disabled by default; configure it per environment after confirming backup coverage.
- Cleanup must be bounded and timestamp-indexed to avoid long locks.
- Archived data must be exported to an approved durable store before deletion; deletion is not archival.
- Every cleanup action must report the retention period, cutoff time, deleted row count, and any error.
- Never clean current/latest state tables, audit records, or active configuration data as part of historical retention.
