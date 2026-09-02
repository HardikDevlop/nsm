# CMDB Verification Report

Date: 2026-08-31
Repository: `/home/agnigate/Desktop/NMS`
Scope: CMDB verification only. No runtime data, configuration, device, SNMP, scheduler, topology, authentication, or other module was changed.

## Verification Boundary

The supplied real-host baseline is authoritative for existing NMS runtime data. This restricted environment was not used to connect to PostgreSQL, SNMP, or the real host, and no replacement runtime check was attempted. The device 115 conclusions below are therefore code-path conclusions cross-checked against the authoritative real-host baseline, not a new live poll.

Status meanings used in this report:

- `PASS`: connected and supported by the current implementation.
- `PARTIAL`: a working path exists, but important data or behavior is incomplete.
- `NOT WIRED`: the required source, trigger, or consumer is absent from the CMDB path.
- `EMPTY-BUT-WORKING`: the endpoint/path can work but currently has no records or no applicable source rows.
- `BLOCKED`: not verified because the required real-host runtime was intentionally not accessible from this environment.

## Executive Result

The current CMDB is a manually managed configuration-item and relationship foundation. Its database tables, protected API routes, relationship service, and read-only frontend are wired. A manual inventory relationship sync can create CIs for active PostgreSQL devices, legacy interfaces, and enabled APM applications. A separate manual topology sync can translate caller-supplied IP links into device-CI relationships.

There is no automatic CMDB synchronization from the existing SNMP scheduler, SNMP identity/inventory persistence, interface polling, VLAN/LLDP collection, topology refresh, or application startup. Existing CIs are deduplicated only by the generated `external_key`, but an existing CI is returned without refreshing any fields. There is no CMDB `last_synchronized`, `first_discovered`, source snapshot, archive operation, or automatic stale/offline lifecycle update.

## Current Architecture

```text
PostgreSQL devices/interfaces/APM applications
                 |
                 |  only when POST /api/v1/cmdb/relationships/sync is called
                 v
       backend.cmdb.service.sync_inventory_relationships
                 |
                 v
cmdb_ci_types + cmdb_configuration_items + contains/runs_on relationships

Caller-supplied topology IP links
                 |
                 |  only when POST /api/v1/cmdb/relationships/sync/topology is called
                 v
       sync_topology_relationships
                 |
                 v
       topology_link relationships between device CIs

CMDB API GET routes -> React CMDB page -> PostgreSQL-backed response
```

Relevant registration is present in `hardik/backend/main.py`: the CMDB router is included at application setup. Startup runs migrations, RBAC seeding, and the normal SNMP scheduler; startup does not call either CMDB sync function.

## Stage Matrix

| Stage | Status | Evidence and boundary |
|---|---|---|
| CMDB database models/tables | PASS | `CIType`, `ConfigurationItem`, `CIRelationship`, and `CIHistory` are registered and have additive migrations. |
| CMDB API route registration | PASS | `/api/v1/cmdb/*` router is included by the FastAPI application. |
| Manual CMDB item CRUD | PASS | Type/item create, list, update, history, and relationship routes exist with RBAC. |
| Inventory relationship sync function | PASS | The service creates device, interface, and application CIs and `contains`/`runs_on` edges when invoked. |
| Automatic inventory synchronization | NOT WIRED | No call from startup, SNMP poll completion, discovery, device CRUD, or scheduler code was found. |
| Scheduled CMDB synchronization | NOT WIRED | The SNMP scheduler is started at startup, but no CMDB job/config/interval is registered. |
| Startup-triggered CMDB synchronization | NOT WIRED | Startup performs migrations/seeding and starts services only; CMDB sync is not called. |
| API/manual inventory synchronization | PASS | `POST /api/v1/cmdb/relationships/sync` invokes the service. |
| Manual topology synchronization | PASS | `POST /api/v1/cmdb/relationships/sync/topology` accepts caller-supplied links. |
| Automatic topology synchronization | NOT WIRED | Existing topology reads/refreshes do not invoke CMDB topology sync. |
| CMDB database to CMDB API | PASS | List/detail-related GET routes query the CMDB tables directly. |
| CMDB API to frontend | PASS | React query functions call the CMDB GET routes through the authenticated API helper. |
| Frontend CMDB mutations/sync controls | NOT WIRED | The page has no create/update/delete/sync action and exposes only reads. |
| Real-host CMDB row population | BLOCKED | Not re-run from this restricted environment, per the requested runtime boundary. |

## Database Models and Tables

### `cmdb_ci_types`

Fields: `id`, unique `name`, `category`, `description`, `created_at`, `updated_at`, `deleted_at`. Categories are limited by the API to `device`, `interface`, `server`, `application`, `database`, `business_service`, and `custom`.

### `cmdb_configuration_items`

Fields: `id`, `ci_type_id`, `name`, nullable `external_key`, `lifecycle_state`, `owner_user_id`, `organization_id`, `device_id`, `interface_id`, `site_id`, `application_id`, `environment`, JSON `attributes`, `created_at`, `updated_at`, and `deleted_at`.

The table has indexes for type/lifecycle, device, site, application, and history lookup. It does not define a unique constraint for `external_key`, `device_id`, or any composite source identity. It also has no typed columns for IP, MAC, vendor, manufacturer, model, serial, firmware, software, operational status, first discovered, last seen, or last synchronized. Such values could currently only be placed in the free-form `attributes` JSON, but the existing sync does not do that.

### `cmdb_ci_relationships`

Fields: `id`, `source_ci_id`, `target_ci_id`, `relationship_type`, `created_at`, and `deleted_at`. There is a database unique constraint on `(source_ci_id, target_ci_id, relationship_type)`, including rows that are soft-deleted.

### `cmdb_ci_history`

Fields: `id`, `ci_id`, `changed_by_user_id`, `action`, `field_name`, `old_value`, `new_value`, and `changed_at`. Manual item updates create history. Automatic synchronization currently creates no history because it does not update existing CIs.

## CMDB API Routes

All routes are under `/api/v1/cmdb` and protected by `cmdb:read` or `cmdb:manage`.

| Route | Behavior |
|---|---|
| `GET /types` | Lists non-deleted CI types. |
| `POST /types` | Creates a CI type. |
| `GET /items` | Lists active CIs with search, type, lifecycle, owner, device, site, and application filters. |
| `POST /items` | Manually creates a CI. |
| `PATCH /items/{ci_id}` | Replaces the complete `CIPayload` fields and records field history. |
| `GET /items/{ci_id}/history` | Reads CI history. |
| `GET /items/{ci_id}/relationships` | Reads active relationships touching the CI. |
| `POST /items/{ci_id}/relationships` | Creates a relationship after existence, duplicate, and cycle checks. |
| `POST /relationships/sync` | Manual inventory/APM-to-CMDB sync. |
| `POST /relationships/sync/topology` | Manual caller-supplied topology-link sync. |

There is no dedicated `POST /sync`, `PUT /sync`, dry-run, status, source-detail, reconciliation, archive, or last-run endpoint.

## Synchronization Behavior

### Inventory sync

`sync_inventory_relationships(db)` currently:

1. Ensures CI types named `device`, `interface`, and `application` exist.
2. Reads non-deleted `Device` rows.
3. Reads all rows from the legacy `interfaces` table without a deleted filter.
4. Reads enabled, non-deleted `APMApplication` rows.
5. Creates or finds device CIs using `external_key = device:{device.id}`.
6. Creates or finds interface CIs using `external_key = interface:{interface.id}`.
7. Creates or finds application CIs using `external_key = application:{application.id}`.
8. Creates device-to-interface `contains` relationships.
9. Creates application-to-device `runs_on` relationships for APM services with a device link.
10. Commits and returns counts.

The `_ci()` helper returns an existing active CI immediately. It does not update `name`, type, lifecycle, links, attributes, timestamps, or history. Consequently this is create-if-missing behavior, not a true synchronization/reconciliation behavior.

### Topology sync

`sync_topology_relationships(db, links)` first runs inventory sync. It then matches existing non-deleted devices by exact IP address and maps `source`/`source_ip` and `target`/`target_ip` values from the caller payload to `device:{id}` CIs. It creates `topology_link` relationships and skips unknown endpoints or duplicate/cyclic links.

It does not query the persisted LLDP table, topology metadata, topology snapshots, or the live topology endpoint. A valid existing topology result must be transformed by the caller into the request payload first.

### Trigger classification

| Trigger | Status | Finding |
|---|---|---|
| Automatic after device creation/update | NOT WIRED | Device CRUD/discovery updates device rows but does not call CMDB sync. |
| Automatic after SNMP poll | NOT WIRED | Poll persistence updates NMS/SNMP tables only. |
| Automatic after identity/inventory discovery | NOT WIRED | Identity discovery updates `device_identity`, capabilities, and the device row, not CMDB. |
| Scheduled | NOT WIRED | No CMDB scheduler job or schedule setting exists. |
| Startup | NOT WIRED | App lifespan does not call CMDB sync. |
| Manual inventory API | PASS | `POST /cmdb/relationships/sync`. |
| Manual topology API | PASS | `POST /cmdb/relationships/sync/topology`. |
| Frontend button/action | NOT WIRED | No frontend function or control calls either sync route. |

## Available Real NMS Sources and Field Mapping

The authoritative baseline records real-host success for device 115 (`Core-switch`) across system identity, interfaces, inventory, VLAN, LLDP, and topology. That proves the source domains exist in the NMS runtime; it does not mean the CMDB currently consumes them.

| Requested CMDB field | Real source(s) available | Current mapping | Status |
|---|---|---|---|
| CI ID | `cmdb_configuration_items.id` | Generated by CMDB database | PASS |
| Device ID | `devices.id` | `ConfigurationItem.device_id` for auto-created device/interface CIs | PASS |
| Hostname | `devices.hostname`; `device_identity.hostname/sys_name` | Device CI name takes `Device.hostname` only; identity is not read | PARTIAL |
| IP address | `devices.ip_address`; identity/topology responses | Not stored in typed CMDB field or sync attributes | NOT WIRED |
| MAC address | `devices.mac_address`; `device_identity.mac_addresses`; interface/system collector output | Not mapped into CMDB | NOT WIRED |
| Device type | `device_types.name`; `device_identity.device_type` | CI type is the generic literal `device`; source device type is not mapped | PARTIAL |
| Vendor/manufacturer | `vendors.vendor_name`; `device_identity.vendor` | Not mapped into CMDB | NOT WIRED |
| Model | `devices.model`; `device_identity.model`; `device_inventory.model` | Not mapped into CMDB | NOT WIRED |
| Serial number | `devices.serial_number`; `device_identity.serial_number`; `device_inventory.serial_number` | Not mapped into CMDB | NOT WIRED |
| Firmware/software version | `devices.firmware_version`; `device_identity.firmware_version`/`os_version`; inventory firmware | Not mapped into CMDB | NOT WIRED |
| Operational status | `devices.status`, `monitoring_status`, `last_seen`; SNMP health/results | New auto CIs are always `lifecycle_state=active`; status is not mapped | PARTIAL |
| Site | `devices.site_id` and `sites` | `site_id` is copied to device CIs only | PARTIAL |
| Organization | `sites.organization_id` and `organizations` | Not copied to device CIs, despite a CMDB `organization_id` column | NOT WIRED |
| Interfaces | Legacy `interfaces` rows and normalized `device_interfaces`/SNMP interface data | Legacy `interfaces` rows create generic interface CIs and `contains` edges; interface fields are not mapped | PARTIAL |
| VLAN | `vlan_information` and VLAN endpoint | Not consumed by CMDB | NOT WIRED |
| Parent/child inventory | Device/interface relation; inventory model data | Device-to-interface `contains` is created; chassis/module inventory hierarchy is not | PARTIAL |
| LLDP relationships | `lldp_neighbors` and LLDP endpoint | Not consumed by CMDB | NOT WIRED |
| Topology relationships | SNMP topology result, topology metadata, manual snapshots | Only caller-supplied IP links can create `topology_link` edges | PARTIAL |
| First discovered | Device/identity `created_at`/`discovered_at` are available | No CMDB field or mapping | NOT WIRED |
| Last seen | `devices.last_seen`, SNMP poll timestamps | No CMDB field or mapping | NOT WIRED |
| Last synchronized | No dedicated source field required for this purpose | No CMDB field, sync-run record, or update behavior | NOT WIRED |
| Device credential metadata | `device_credentials` and encrypted SNMP credential metadata | Not read by CMDB sync; this is appropriate for avoiding secret exposure | EMPTY-BUT-WORKING |
| APM application/service | `apm_applications`, `apm_services` | Application CIs and `runs_on` edges are created when the manual sync runs | PASS for current narrow scope |

### Safe credential handling

The CMDB sync does not need device credentials and does not copy secret material. Credential metadata such as SNMP version could be exposed only as a non-secret attribute if explicitly required later; passwords, communities, auth keys, privacy keys, and API tokens must not be copied into CMDB.

## Device 115: Core-switch

The authoritative baseline identifies device 115 as a real monitored SNMP v3 device and records successful system identity, interfaces, inventory, VLAN, LLDP, and topology collection. CPU and memory are unsupported by that device, which is unrelated to CMDB synchronization.

Based on the current code path, device 115 can be synchronized without adding device-side configuration:

- The inventory sync reads the existing PostgreSQL `devices` row by normal active-device query; it does not require a new credential or SNMP request.
- It will create or find `external_key = device:115`, use the current `devices.hostname` as the CI name, set `device_id=115`, copy `site_id`, and set lifecycle to `active` only when the CI is newly created.
- Any existing rows in the legacy `interfaces` table for device 115 can produce interface CIs and `contains` relationships.
- Existing SNMP identity, inventory, VLAN, LLDP, and topology data will not be copied automatically by this sync.
- The operation remains manual because the current code has no automatic invocation. No live call was made for this report.

Therefore: `PASS` for basic device-to-CI creation capability, `PARTIAL` for useful CMDB synchronization of Core-switch, and `NOT WIRED` for complete real NMS identity/inventory/topology enrichment.

## Deduplication and Update Behavior

### Current keys

The sync strategy uses these generated keys:

- Device: `device:{devices.id}`
- Interface: `interface:{interfaces.id}`
- Application: `application:{apm_applications.id}`

The lookup is global on active `external_key`. This is a deterministic strategy for the current device-row identity, but the database does not enforce uniqueness and the manual API accepts a nullable, caller-supplied key.

### Duplicate risks

- Manual `POST /items` can create multiple CIs for the same `device_id`, `interface_id`, or real-world device because no uniqueness validation exists.
- A manually created CI with a different or null external key can coexist with an auto-generated CI for the same device.
- A soft-deleted CI is ignored by `_ci()`, and a new CI with the same external key can then be created. The database has no external-key uniqueness constraint to prevent this.
- Concurrent sync calls are not protected by a CMDB-specific lock or database upsert constraint.

### Existing-information changes

CMDB does not update an existing CI when device hostname, IP, vendor, model, serial, firmware, identity, interface, or status data changes. `_ci()` returns the existing object before any refresh logic. There is consequently no update history for source changes and `updated_at` is not a synchronization timestamp.

## Deletion, Offline, and Lifecycle Behavior

- Device sync filters out devices with `Device.deleted_at` set, but does not find or archive/delete their existing CIs.
- Offline devices are not excluded from sync. If their device row is active, a newly created CI is marked `lifecycle_state=active` regardless of `Device.status` or `last_seen`.
- No automatic transition to `maintenance`, `retired`, or `disposed` exists.
- CMDB item list filters out soft-deleted CIs, but there is no CMDB delete/archive API in the inspected routes.
- Interface rows are read without a deleted filter because the legacy `Interface` model has no `deleted_at` field.

Classification: `PARTIAL` for retention of active CMDB records, `NOT WIRED` for source deletion/offline reconciliation, and `NOT WIRED` for archival lifecycle management.

## Relationship Behavior

Persisted relationships are supported by `cmdb_ci_relationships` and are returned by the API/frontend.

Current automatically generated relationship types are:

- `contains`: device CI to legacy interface CI.
- `runs_on`: application CI to device CI for linked APM services.
- `topology_link`: device CI to device CI only from the manual topology request payload.

The relationship service rejects missing CIs, active duplicates, and cycles. A database uniqueness constraint also exists. Relationships are not automatically removed when source links disappear, and LLDP/VLAN/inventory hierarchy relationships are not persisted by the current sync. A soft-deleted relationship still participates in the database unique constraint, which can prevent recreating the same triple without a dedicated restore/reconciliation path.

Classification: `PASS` for manual persistence and readback, `PARTIAL` for current proven device/interface/application relationships, and `NOT WIRED` for automatic LLDP/topology/inventory reconciliation.

## Frontend Verification

The CMDB page is `figma design/src/pages/CMDB.tsx` and is mounted at `/cmdb` behind `cmdb:read` permission. The sidebar and route prefetch map are also wired.

The page uses authenticated React Query calls for:

- `GET /cmdb/types`
- `GET /cmdb/items` with search/type/lifecycle/device/site filters
- `GET /cmdb/items/{id}/relationships`
- `GET /cmdb/items/{id}/history`
- `GET /devices/options`
- `GET /sites`

The API helper builds requests under `/api/v1`, loads the existing token from local storage, and sends authenticated requests. The TypeScript interfaces mirror the CMDB response fields.

The UI renders the API results, selected CI details, JSON `attributes`, relationships, and history. No static/mock CMDB records were found in the page. It does not call the CMDB create, update, relationship-create, inventory-sync, or topology-sync routes. It also uses `refetchOnMount: false` for the item query, so the displayed list may remain cached until its query key changes or the cache is otherwise invalidated.

Classification: `PASS` for actual PostgreSQL-backed read display, `PARTIAL` for operational usability, and `NOT WIRED` for synchronization controls and mutation/reconciliation UI.

## Exact Missing Path

```text
Existing NMS data
  devices -------------------------------> CMDB device CI creation: PARTIAL
  identity/inventory --------------------> CMDB attributes/updates: NOT WIRED
  interfaces ----------------------------> generic interface CIs: PARTIAL
  VLAN/LLDP ------------------------------> CMDB CIs/edges: NOT WIRED
  topology ------------------------------> only manual payload path: PARTIAL
  sites/organizations -------------------> site only, organization absent: PARTIAL
  credential metadata -------------------> intentionally not consumed: EMPTY-BUT-WORKING

CMDB synchronization
  manual inventory endpoint --------------> PASS
  manual topology endpoint ---------------> PASS
  startup/scheduler/poll triggers --------> NOT WIRED
  reconciliation/update/archive ----------> NOT WIRED

CMDB database
  foundation tables ----------------------> PASS
  typed source fields/timestamps ---------> NOT WIRED
  source-change history ------------------> NOT WIRED

CMDB API
  read/list/history/relationships --------> PASS
  sync endpoint --------------------------> PASS, manual only
  sync status/dry-run/archive ------------> NOT WIRED

CMDB frontend
  authenticated PostgreSQL-backed reads ---> PASS
  source enrichment display --------------> PARTIAL
  sync/mutation controls -----------------> NOT WIRED
```

## Minimum Implementation Required

No implementation was made in this verification task. To achieve automatic synchronization while preserving the frozen core NMS, the minimum CMDB-only implementation would be:

1. Add a CMDB reconciliation service that reads existing PostgreSQL `Device`, `DeviceIdentity`, `DeviceInventory`, `Interface`/normalized interface, `Site`, `Organization`, and relevant persisted topology/LLDP records without initiating new device configuration.
2. Define an explicit source identity policy. Keep `device:{device_id}` as the authoritative device key, enforce uniqueness for active source CIs, and handle manual-vs-synchronized ownership explicitly.
3. Upsert existing CIs, including safe source fields in `attributes` or additive typed columns, while preserving user-owned overrides.
4. Add synchronization metadata such as source, first discovered, last seen, last synchronized, and reconciliation outcome. Write CI history when source values actually change.
5. Reconcile interfaces and proven parent/child, LLDP, and topology relationships; remove or soft-retire relationships that are no longer present according to a defined source policy.
6. Define offline/deleted behavior separately: retain evidence, mark inactive/retired, or archive, rather than silently deleting CIs.
7. Invoke the reconciliation from an existing safe application lifecycle/scheduler integration or expose a controlled manual/API job with status and locking. The trigger must not perform a second SNMP poll when persisted source data is sufficient.
8. Add a read-only sync status and source-details view to the CMDB frontend; add mutation/sync controls only with the existing CMDB permissions.
9. Add CMDB-focused tests for device 115-shaped data, idempotency, changed identity fields, duplicate/manual collision, offline/deleted source rows, relationship removal, and concurrent sync. Tests must use fixtures only in tests and must not alter real runtime data.

## Final Classification

| Capability | Classification |
|---|---|
| CMDB schema foundation | PASS |
| Protected CMDB API | PASS |
| PostgreSQL-backed CMDB frontend reads | PASS |
| Manual device/interface/application CI creation | PASS |
| Device 115 basic CI creation capability | PASS |
| Complete device identity/inventory mapping | NOT WIRED |
| CI refresh when source data changes | NOT WIRED |
| Automatic synchronization | NOT WIRED |
| Scheduled synchronization | NOT WIRED |
| Startup synchronization | NOT WIRED |
| Automatic VLAN/LLDP/topology synchronization | NOT WIRED |
| Offline/deleted lifecycle reconciliation | NOT WIRED |
| Duplicate protection for all CI creation paths | PARTIAL |
| Persisted manual and narrow sync relationships | PASS |
| Full source relationship reconciliation | NOT WIRED |
| Live CMDB runtime row count in restricted environment | BLOCKED |
