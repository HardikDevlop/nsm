# Soft Light Theme Visual Rebalance Report

## Changes made

The existing `ThemePicker → ThemeContext → CSS variables` architecture was preserved. Light mode was rebalanced centrally instead of adding page-specific palette logic.

- Light application background: changed from near-white `#f5f7fb` to a soft cool gray.
- Light cards: changed from pure white to soft off-white.
- Light primary text: strengthened to dark navy/slate.
- Light muted/secondary text: strengthened for timestamps, metadata, MAC/IP values, VLAN data, subtitles, and helper text.
- Table header, row, and hover tokens now provide visible but restrained separation.
- Dark defaults and custom palette persistence remain separate and unchanged.

## Semantic hierarchy

`--t-bg` is the soft application background, `--t-card` is the primary surface, `--t-text` is the primary foreground, `--t-text-secondary` is readable secondary content, `--t-muted` remains the muted hierarchy, and table tokens provide a neutral header/row/hover progression. Borders remain subtle but visible.

## MAC and VLAN handling

The existing MAC/FDB readability work now inherits the softer global table hierarchy. Port Summary and mapping chips use semantic table/text tokens; the 2D MAC topology remains an intentional dark visualization canvas. VLAN/module tables inherit the shared table header, row, border, and hover rules rather than receiving page-specific colors.

## Preserved exceptions

Topology, MAC topology, packet diagrams, charts, device illustrations, and semantic status colors retain intentional visualization colors. Online remains green, offline remains red, and degraded remains amber. Manual Topology offline-red rendering remains intact.

## Validation

- Theme regression tests: **PASS**
- Manual Topology regression tests: **PASS**
- Shared topology graph test: **PASS**
- Device identity regression test: **PASS**
- Frontend build: **PASS**
- Backend changed: **NO**
- Browser/runtime verification: **NOT RUN**

## Final status

```text
SOFT LIGHT GLOBAL PALETTE: PASS
GLARE REDUCED SOURCE-SIDE: PASS
PRIMARY TEXT READABLE: PASS
SECONDARY TEXT READABLE: PASS
MUTED TEXT READABLE: PASS
SURFACE HIERARCHY: PASS
GLOBAL TABLE STYLE: PASS
PORT SUMMARY: PASS
MAC MAPPING CHIPS: PASS
RAW MAC TABLE: PASS
VLAN INVENTORY: PASS
DARK VISUALIZATION TRANSITIONS: PASS
STATUS SEMANTIC COLORS PRESERVED: PASS
MANUAL TOPOLOGY OFFLINE RED PRESERVED: PASS
DARK THEME PRESERVED: PASS
CUSTOM THEME PRESERVED: PASS
THEME TESTS: PASS
MANUAL TOPOLOGY TESTS: PASS
FRONTEND BUILD: PASS
BACKEND CHANGED: NO
RUNTIME/BROWSER VERIFIED: NO
```
