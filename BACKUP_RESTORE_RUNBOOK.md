# NMS Backup and Restore Runbook

This runbook covers the existing PostgreSQL database, application configuration, and encrypted device-configuration versions. It does not claim disaster-recovery success until the restore validation procedure has completed and its evidence has been recorded.

## Backup scope

- PostgreSQL: all NMS tables, migrations, devices, credentials, monitoring jobs, metrics, alerts, topology, CMDB, flow/APM data, and audit history.
- PostgreSQL WAL: continuous archiving is required for point-in-time recovery.
- Application configuration: deployment environment files and secret-management references, stored outside Git with restricted permissions. Never place plaintext SNMP credentials in the backup directory.
- Device configurations: use the existing `/api/v1/config-backups/capture` endpoint. Content is encrypted by the application, checksummed, versioned, and deduplicated.

## Automated PostgreSQL backup

Set these values in the backup host environment or a protected systemd EnvironmentFile:

```bash
export PGHOST="postgres-primary.example.internal"
export PGPORT="5432"
export PGUSER="nms_backup"
export PGDATABASE="nms"
export BACKUP_ROOT="/srv/backups/nms"
export RETENTION_DAYS="35"
```

Use a dedicated least-privilege backup role and `.pgpass` with mode `0600`. Run a nightly custom-format backup, which supports selective restore and parallel `pg_restore`:

```bash
set -euo pipefail
day="$(date -u +%Y%m%dT%H%M%SZ)"
dir="$BACKUP_ROOT/$day"
mkdir -p "$dir"
chmod 700 "$dir"
pg_dump --format=custom --no-owner --file="$dir/nms.dump" "$PGDATABASE"
pg_dump --schema-only --no-owner --file="$dir/schema.sql" "$PGDATABASE"
sha256sum "$dir/nms.dump" "$dir/schema.sql" > "$dir/SHA256SUMS"
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime +"$RETENTION_DAYS" -exec rm -rf -- {} +
```

Schedule this from a protected systemd timer or cron on the backup host, not from every FastAPI instance. Copy completed backup directories to an independent encrypted storage target before applying retention. Keep at least one offline/immutable copy according to the organization’s RPO.

## WAL and configuration backup

Configure PostgreSQL `archive_mode=on`, a tested `archive_command`, and monitor failed archive counts. Store the application’s environment/secret references and deployment manifests in the organization’s secret manager or encrypted backup vault. Back up the encryption-key material separately from encrypted device configuration rows; without the key, configuration content cannot be restored.

Device configuration captures are initiated through the existing authenticated API by a scheduled job or authorized operator. Confirm the response contains `version`, `checksum`, `captured_at`, and `captured_by`; an unchanged capture must not create a new version but remains auditable.

## Restore procedure

1. Declare the incident, record the target recovery timestamp, and stop writes to the isolated restore database. Do not overwrite production until validation is approved.
2. Provision a clean PostgreSQL instance with the supported PostgreSQL version and extensions.
3. Restore the selected dump:

```bash
createdb "$PGDATABASE"
pg_restore --clean --if-exists --no-owner --dbname="$PGDATABASE" "$dir/nms.dump"
```

4. For point-in-time recovery, restore the base backup and WAL archive to a separate instance using PostgreSQL recovery configuration, stopping at the recorded target timestamp.
5. Start the application against the isolated database, run the application-managed migrations once, and verify the migration status endpoint and schema version.
6. Restore secret/encryption keys through the approved secret manager. Never edit encrypted credential/configuration rows manually.
7. Validate login/RBAC, device inventory, SNMP credential decryption, monitoring-job restoration, alerts, topology, reports, configuration versions/diffs, CMDB, flow, and APM reads.
8. Compare row counts/checksums for critical tables and inspect recent audit records.
9. Only after sign-off, redirect the controlled application endpoint. Keep the original database preserved for forensic recovery.

## Restore validation record

Every exercise or incident must record:

- Backup identifier, dump checksum, WAL target, and restore host.
- Restore start/end UTC timestamps.
- Migration status and critical-table row-count comparison.
- Results for login/RBAC, devices, monitoring, alerts, topology, reports, configuration backups, and key integrations.
- Operator, reviewer, failures, corrective actions, and evidence paths.

An unexecuted procedure is **not** a successful DR test. The repository currently contains the procedure only; populate a dated validation record after running it against a disposable restore target.

## Operational checks

- Alert when the last successful dump is older than 24 hours.
- Alert on checksum failure, missing WAL archives, backup-storage capacity, replication lag, and restore-validation age.
- Perform a monthly disposable restore test and a quarterly point-in-time recovery test, or more often if the service RPO requires it.
- Review retention and encryption access quarterly; restrict backup reads to the backup/recovery role.
