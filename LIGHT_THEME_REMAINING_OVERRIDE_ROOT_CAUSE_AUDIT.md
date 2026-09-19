# Light Theme Remaining Override Root-Cause Audit

Audit mode: read-only. No code, CSS, tests, or backend files were changed.

## Executive finding

The remaining washed-out/low-contrast behavior is not caused by the global light palette alone. It is primarily caused by component-local inline styles and dark-oriented structural backgrounds in the reusable SNMP collector surface. The existing token rules do target some of the affected nodes, but they are incomplete and cannot reliably replace every inline declaration—especially gradients and styles outside the scoped selector.

## 1. Exact MAC Port Summary source

Primary component: `figma design/src/features/snmp/components/SNMPCollectorDataCard.tsx`.

The `PORT SUMMARY` section begins around line 307. The table and mappings are rendered in this component:

- table headings: `Port`, `Classification`, `MAC Count`, `VLANs`, `Device MAC → IP Mapping`
- rows: `enrichedPortGroups.map(...)`
- mapping chips: `group.device_mappings.map(...)`

The surrounding 2D visualization is `figma design/src/features/snmp/components/MacPortTopology2D.tsx` and is an intentional dark visualization canvas, not the primary bug.

## 2. Winning source-level styles

| Visible element | Current source | Classification | Why it bypasses normal theme flow |
|---|---|---|---|
| Large Port Summary row background | `SNMPCollectorDataCard.tsx:355-359`: inline `background: index % 2 ? rgba(8,25,55,.18) : transparent` | Structural hard-coded color | Inline style is the component’s direct row surface; the previous CSS override only catches it through an attribute selector and relies on `!important`. |
| Table header | line 343: inline `background: "#081937"`, color `#8899bb` | Structural hard-coded color | Inline background is dark blue and is not a semantic token. The scoped CSS can override color/background only where selector matching and order win. |
| Mapping chip background | line 398: inline `background: rgba(8,25,55,.28)` | Structural hard-coded color | Same dark blue-gray chip surface; it is not derived from `--t-table-row` or `--t-card`. |
| Mapping MAC text | line 401: `#f1f5f9` when resolved, `#77859b` otherwise; label `#8899bb` | Structural/secondary hard-coded color | These values are chosen in JSX and only conditionally overridden by the scoped attribute selectors. |
| Mapping IP text | line 402: `#67e8f9` when resolved, `#77859b` otherwise | Accent/secondary hard-coded color | It is semantically accent-colored but remains a fixed cyan/gray pair rather than the active accent and secondary tokens. |
| Port/MAC/VLAN cell values | lines 363, 382, 388, 474: `#c8d8ee` | Structural foreground | Fixed pale blue-gray foreground; low contrast when the surrounding surface is light. |
| Port Summary subtitle/labels | lines 318, 325, 429, 488, 508: `#667799`/`#8899bb` | Secondary/muted hard-coded colors | These are readable in dark mode but fragile in a custom/light palette. |
| Summary cards | lines 275 and 423: dark `rgba(...)` / dark gradients | Structural hard-coded surfaces | Creates abrupt dark nested cards or excessive contrast against light page surfaces. |
| Bottom raw table | lines 456 and 497: dark `rgba(...)` backgrounds; values line 474 `#c8d8ee` | Structural hard-coded surface/foreground | Bypasses table tokens. |
| 2D topology canvas | `MacPortTopology2D.tsx:76-80`, dark gradients and cyan grid | Visualization color — keep | Explicitly allowed dark visualization exception. |

## 3. Cascade/specificity findings

`figma design/src/index.css` contains the previous rules around lines 30–50:

- `.snmp-collector-card [style*="#c8d8ee"]`, `#8899bb`, `#667799`, etc. set `color: var(--t-text) !important`.
- `.snmp-collector-card [style*="rgba(8,25,55"]` sets background/border with `!important`.
- `.snmp-collector-card table th` sets table header background/color with `!important`.
- `.snmp-mac-topology` only changes inherited color and selected muted text.

These rules do target the Port Summary component because `SNMPCollectorDataCard` supplies the `snmp-collector-card` class and `MacPortTopology2D` supplies `snmp-mac-topology`. However:

1. They are attribute-selector patches against literal strings, not a stable semantic contract.
2. They do not cover all structural declarations, notably the header/summary gradients and the many non-SNMP components with similar literals.
3. Inline styles remain the originating source; only the selectors carrying `!important` can override them.
4. Rules later in `index.css`, page-local selectors, or other `!important` rules can win based on specificity/order.
5. Theme variables being defined does not prove that a given nested surface consumes them.

The cascade is therefore a mixed state: some MAC styles are overridden in light mode, while other component-local styles remain dark-oriented or are covered only accidentally by literal matching.

## 4. Repository-wide repeated patterns

Source search under `figma design/src` found approximately:

- `rgba(`: 1,221 occurrences
- `#c8d8ee`: 221 occurrences
- `#8899bb`: 522 occurrences
- `#667799`: 128 occurrences
- `opacity-`: 118 occurrences
- `!important`: 197 occurrences
- `#081937`: 1 direct occurrence in the Port Summary header
- `bg-blue-50` / `bg-blue-100`: 0 occurrences

These counts show the problem is a broad legacy inline-color pattern, not a single MAC-table typo. The repeated blue-gray values appear in SNMP detail/module pages, device detail, IP Scan, and other data surfaces. The repeated `rgba(...)` patterns include both structural UI and legitimate visualization/semantic styling, so blanket replacement would be unsafe.

## 5. Shared component audit

| Component | Assessment | Cause/impact |
|---|---|---|
| `SNMPCollectorDataCard` | **PARTIAL / BYPASSES THEME** | Shared collector wrapper for module data; contains the Port Summary, MAC mappings, summary cards, and raw table with inline structural colors. |
| `MacPortTopology2D` | **INTENTIONAL VISUALIZATION; surrounding UI PARTIAL** | Dark canvas is acceptable; headings, controls, helper labels, and borders still use fixed blue-gray values. |
| `GlassCard` | **THEME SAFE** | Uses `.glass` and active CSS variables for surface/border. |
| `ThemeContext` | **THEME SAFE as authority** | Correctly owns mode/custom palette/persistence; not the direct source of the nested MAC colors. |
| global table rules | **PARTIAL** | Provide defaults, but page/component inline styles and later selectors can override or require brittle `!important` patches. |
| badges/controls | **MIXED** | Shared pieces are mostly token-aware; many pages still contain local fixed status/visualization colors. |

## 6. Impact map

| Page/component | Likely offending source | Shared/local | Token bypassed? | Recommended fix location | Risk |
|---|---|---|---|---|---|
| MAC Table / Port Summary | `SNMPCollectorDataCard.tsx` inline table/chip styles | Shared SNMP component | Yes | Refactor structural inline styles to semantic variables/classes | Medium |
| VLAN | Shared collector card/module tables plus local module renderers | Shared + local | Often | Same collector/table contract; preserve VLAN semantic values | Medium |
| ARP/Routing/LLDP/CDP | `SNMPCollectorDataCard` and module wrappers | Shared | Often | Shared collector/table styling | Medium |
| Interfaces/Inventory | SNMP module pages and detail cards | Shared + local | Repeated blue-gray literals | Shared SNMP data presentation layer | Medium |
| SNMP Devices/detail | page-local inline colors and detail CSS | Local/shared | Yes | Detail wrapper/shared data tokens | Medium |
| Device Monitoring/Linux Server Monitoring | page-local tables/cards | Local | Some | Shared table/input tokens, then narrow local exceptions | Medium |
| Packet Analysis | dark graph/flow visualization plus surrounding controls | Mixed | Visualization intentional | Keep canvas; fix surrounding surfaces | Low/Medium |
| Alerts/Events/Logs | severity colors plus local table/modal surfaces | Mixed | Status colors intentional | Shared modal/table surfaces | Medium |
| Management tables | repeated inline borders/hover backgrounds | Local repeated pattern | Often | Shared table contract | Medium |

## 7. Exceptions to preserve

Keep semantic status colors: green success/online, red error/offline, amber warning/degraded, and accent colors used to distinguish data series. Keep dark topology/MAC/packet/device-diagram canvases. Do not treat those visualization surfaces as the primary structural readability defect.

## 8. Correct fix layer

The minimal safe fix is a combination:

1. Refactor `SNMPCollectorDataCard.tsx` structural table/card/chip inline styles to semantic CSS variables/classes. Do not alter classification/status colors.
2. Refactor the surrounding readable labels/controls in `MacPortTopology2D.tsx` to semantic variables while retaining its dark canvas.
3. Strengthen the shared table component/CSS contract only after removing conflicting component-local inline backgrounds.
4. Use the same semantic contract in the shared SNMP module wrapper so VLAN, ARP, Routing, LLDP/CDP, Interfaces, Inventory, and MAC Table converge.
5. Leave `ThemeContext.tsx` as the authority; do not add another palette system.

## Files that would need modification for the recommended fix

- `figma design/src/features/snmp/components/SNMPCollectorDataCard.tsx`
- `figma design/src/features/snmp/components/MacPortTopology2D.tsx`
- likely `figma design/src/index.css` for stable shared table/chip classes
- focused theme regression tests

## Files that must not be modified for this diagnosis/fix

No backend, API, database, SNMP, ICMP, scheduler, Redis, alerting, device-health, topology reconciliation, or data-collection files should be changed. Visualization canvas rules should remain intentionally specialized.

## Final status

```text
GLOBAL THEME SWITCH WORKING: YES (source architecture)
PROBLEM IS GLOBAL TOKEN VALUES ONLY: NO
COMPONENT OVERRIDES FOUND: YES
INLINE COLORS FOUND: YES
HARDCODED TAILWIND COLORS FOUND: YES
CSS SPECIFICITY ISSUE FOUND: YES (mixed inline/!important/selector-order cascade)
SHARED ROOT CAUSE FOUND: YES
MAC PORT SUMMARY ROOT CAUSE: IDENTIFIED
MAC CHIP ROOT CAUSE: IDENTIFIED
LOW-CONTRAST TEXT ROOT CAUSE: IDENTIFIED
MULTIPLE PAGES SHARE SAME CAUSE: YES
SAFE SHARED FIX POSSIBLE: YES
CODE CHANGED: NO
```
