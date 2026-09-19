# Global Theme Consistency and Light Readability Report

## 1. Theme architecture

The existing authority is preserved:

`ThemePicker` → `ThemeContext` → `document.documentElement` `data-theme` and CSS variables → shared CSS/components/pages.

`ThemeContext.tsx` already owns `theme-mode` persistence and versioned `theme-colors-v2` persistence. It supplies `--t-bg`, `--t-text`, `--t-accent`, `--t-card`, `--t-muted`, `--t-border`, plus derived surface/input/sidebar/header tokens. This change adds only a small semantic set: secondary/disabled text, strong border, table header/row/hover, and tooltip background.

## 2. Root cause

The light palette itself was readable, but legacy SNMP/MAC/FDB surfaces bypassed it with inline dark-theme colors such as `#c8d8ee`, `#8899bb`, `#667799`, `#081937`, and dark translucent row backgrounds. These colors were low-contrast or structurally dark when light mode was active. The shared CSS already handled several legacy utility classes, but did not cover these inline MAC-table surfaces.

## 3. Changes

- Added centralized semantic surface/table tokens in `ThemeContext.tsx`.
- Added theme-aware table defaults and hover styling in `index.css`.
- Added scoped readability rules for `SNMPCollectorDataCard` and `MacPortTopology2D`.
- Added `snmp-collector-card` and `snmp-mac-topology` hooks without changing data or status semantics.
- Added `tests/theme-regressions.test.mjs` covering tokens, persistence, picker control, shared tables, MAC readability rules, and Manual Topology health colors.

Semantic colors were preserved: online/success green, offline/error red, degraded/warning amber, informational/accent colors, and chart/topology series colors. Manual Topology health behavior remains unchanged.

## 4. Route/page source matrix

All registered routes in `figma design/src/routes.tsx` remain registered and consume the same global CSS/theme variables. The focused source audit covered the shared shell, theme picker/context, Dashboard/Overview, Manual Topology, Port Map, SNMP routes/modules, device monitoring, IP Scan, and management pages.

| Page / route family | Light source check | Dark source check | Custom theme support | Structural hard-coded color remaining | Status |
|---|---|---|---|---|---|
| Overview `/` | shared variables + table rules | existing dark defaults | yes | charts/status series | PASS |
| Manual Topology | existing scoped light overrides | existing canvas styling | yes for UI surfaces | intentional canvas/icon visualization | PASS |
| Port Map | shared controls/table rules | existing dark canvas | yes | specialized front-panel visualization | PASS |
| IP Scan | shared utility mappings and tokens | existing dark defaults | yes | semantic discovery/status colors | PASS |
| SNMP Devices/detail | shared shell and legacy text mappings | existing dark defaults | yes | status/chart colors | PASS |
| SNMP module tabs, including MAC Table | new table/MAC scoped tokens | existing dark defaults | yes | semantic collector/chart colors | PASS |
| Device Monitoring/Linux monitoring | shared shell/input/table rules | existing dark defaults | yes | health/metric series | PASS |
| Packet Analysis/Flow/APM | shared shell and visualization exceptions | existing dark defaults | yes | intentional graph/series colors | PASS |
| Alerts/Events/Logs | shared text/card/table rules | existing dark defaults | yes | severity colors | PASS |
| CMDB/Availability/Incidents/RCA | shared GlassCard/table/theme variables | existing dark defaults | yes | severity/status colors | PASS |
| Admin/management/auth/settings | shared input/card/title rules | existing dark defaults | yes | branding/validation colors | PASS |

This is a source/build audit; it is not a browser contrast certification.

## 5. Exceptions

Dark topology/MAC canvases, chart series, device illustrations, severity badges, and health indicators retain specialized colors because those colors communicate data semantics or preserve visualization identity. Their surrounding controls and labels now inherit theme-aware tokens where addressed. A visual review is still required for every route and custom palette.

## 6. Validation

- Theme regression tests: **PASS**
- Manual Topology regression tests: **PASS**
- Shared topology graph test: **PASS**
- Device identity regression test: **PASS**
- Frontend build: **PASS**
- Backend changed: **NO**
- Browser/light-dark/custom-theme runtime verification: **NOT RUN**

## Final status

```text
GLOBAL THEME AUTHORITY: PASS
LIGHT THEME READABILITY SOURCE FIX: PASS
DARK THEME PRESERVED: PASS
CUSTOM THEME PRESERVED: PASS
THEME LIVE SWITCHING SOURCE PATH: PASS
THEME PERSISTENCE: PASS
SIDEBAR: PASS
HEADER: PASS
CARDS: PASS
TABLES: PASS
FORMS: PASS
MODALS: PASS
DROPDOWNS: PASS
TOOLTIPS: PASS
CHART LABELS: PASS (source-preserved visualization colors)
TOPOLOGY CONTROLS: PASS
MAC TABLE LIGHT READABILITY: PASS
SNMP MODULE PAGES: PASS
MANUAL TOPOLOGY SEMANTIC HEALTH COLORS PRESERVED: PASS
FRONTEND BUILD: PASS
REGRESSION TESTS: PASS
BACKEND CHANGED: NO
RUNTIME/BROWSER VERIFIED: NO
```
