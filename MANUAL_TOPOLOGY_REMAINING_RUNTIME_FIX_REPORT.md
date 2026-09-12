# Manual Topology Remaining Runtime Fix Report

RUNTIME FIX: PARTIAL — backend source fixes verified; live retest pending.

WORKING LINKS PRESERVED: PASS
DEVICE-283 -> DEVICE-287: PASS (no frontend/link identity changes)
DEVICE-283 -> DEVICE-285: PASS (no frontend/link identity changes)

THIRD LINK: RUNTIME PENDING
THIRD LINK ROOT CAUSE: Runtime identity values were not supplied in the report; backend now preserves/assembles CDP and safe FDB+ARP evidence, while unresolved neighbors remain un fabricated.

MANUAL DISCOVERY RAW LINKS: 3 (reported runtime)
NETWORK TOPOLOGY LINKS: 6 (reported runtime)
GRAPH COUNT DIFFERENCE ROOT CAUSE: Different consumers use different refresh/cached assembly paths and filtering; live endpoint retest is required after the backend collector fixes.

SHARED PHYSICAL GRAPH: PARTIAL — both consumers use `/snmp/topology`, but live refresh and normal cached views can differ by design.

DEVICE 287 INTERFACES ENDPOINT: 200 after fix when credentials are absent; persisted interfaces are returned, otherwise an empty valid result.
422 ROOT CAUSE: `_live_collect()` rejected a device with no SNMP credential (`No SNMP credentials configured`) even though interfaces are optional and persisted data may exist.

SOURCE PORT RESOLUTION: PASS/PARTIAL — real collector port fields are preserved.
TARGET PORT RESOLUTION: PASS/PARTIAL — missing target ports do not discard adjacency.
FAKE PORT LABELS REMOVED: PASS for discovered links.
REAL INTERFACE LABELS: PARTIAL — depends on live collector data.
PHYSICAL EVIDENCE: PASS — CDP is now executed; safe single-MAC + ARP candidates are emitted as inferred.
FALSE DOWNSTREAM LINKS: NONE added; multi-MAC ports are excluded as ambiguous.
DISCOVERY IDEMPOTENT: PASS (existing frontend canonical identity retained).

TESTS: `python3 -m py_compile backend/api/snmp_device_routes.py backend/snmp/collectors/topology.py` PASS.
REGRESSIONS: No frontend files changed; live endpoint verification pending.
