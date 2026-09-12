# Manual Topology Discovery Target Mapping Report

TARGET MAPPING FIX: PASS (source/build verified; live retest pending)

CURRENT RAW DEVICES: 50 in the reported runtime

CURRENT RAW LINKS: 1 in the reported runtime

FAILING LINK SOURCE: Captured by `DISCOVERY_LINK_TRACE` without credentials.

FAILING LINK TARGET: Previously unresolved by the canvas-only resolver; now checks numeric/string ID, management-IP aliases, canonical chassis/MAC, exact hostname, and unique short hostname.

ROOT CAUSE: The previous resolver did not canonicalize MAC/chassis identities and did not accept target management-IP, remote-system-name, or chassis aliases. It also reported every failed target as “target device not found” without distinguishing unresolved/unmanaged neighbors.

TARGET EXISTS IN TOPOLOGY DEVICE LIST: Runtime retest pending; the new trace reports this explicitly.

TARGET MATCHED BY: ID / IP / MAC / HOSTNAME / NONE, emitted by `DISCOVERY_LINK_TRACE`.

TARGET MANAGED IN NMS: Determined by successful canvas-node resolution; unmanaged/unresolved targets are classified explicitly.

TARGET CANVAS NODE FOUND: Runtime retest pending.

LINK CREATED AFTER FIX: Runtime pending.

PORT DATA: PARTIAL allowed; missing ports no longer block adjacency.

FRONTEND MAPPING: PASS — deterministic normalization and resolution order added.

BACKEND NORMALIZATION: PASS — backend route was already verified to return assembled topology; no collector internals changed.

UNMANAGED NEIGHBOR HANDLING: PASS — no fake device is created; trace reason is `UNMANAGED_OR_UNRESOLVED_DEVICE`.

TESTS: `npm run build` PASS. Live runtime retest pending.

REGRESSIONS: NONE observed by production build.
