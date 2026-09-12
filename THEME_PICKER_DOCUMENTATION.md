# NMS Theme Picker Documentation

## Overview

NMS ka **Theme Picker** top navigation bar ke color/palette button se open hone wala right-side customization panel hai. Isse user application ke primary visual colors ko live change kar sakta hai.

## User interface

- Panel screen ke right side se slide/open hota hai aur 320px wide hai.
- Background par click karne se panel close hota hai.
- Close icon se bhi panel band kiya ja sakta hai.
- Panel mein ye 6 color controls available hain:
  - **Background** – application/page background
  - **Text** – main text color
  - **Accent** – primary highlight, buttons aur active elements
  - **Card / Panel** – cards, panels aur surfaces
  - **Muted Text** – secondary/less prominent text
  - **Border** – borders aur separators
- Har control mein native color picker, current HEX value aur predefined color swatches hote hain.
- **Reset to Default** button current theme ke default colors restore karta hai.

## Light and dark themes

Top bar ka **LIGHT/DARK** toggle light aur dark mode switch karta hai. Toggle tabhi active hota hai jab branding configuration mein ek se zyada themes allowed hon.

Default palettes:

| Token | Dark | Light |
|---|---|---|
| Background | `#000000` | `#f0f2f5` |
| Text | `#e2e8f5` | `#1a1a2e` |
| Accent | `#FF0015` | `#FF0015` |
| Card / Panel | `#0f0f0f` | `#ffffff` |
| Muted Text | `#888888` | `#666666` |
| Border | `#1e1e1e` | `#e0e0e0` |

## Technical behavior

Implementation files:

- `figma design/src/components/ThemePicker.tsx` – picker UI and color swatches.
- `figma design/src/components/ThemeContext.tsx` – theme state, defaults, persistence and CSS variable updates.
- `figma design/src/components/Layout.tsx` – top-bar buttons and picker open/close state.
- `figma design/src/components/BrandingContext.tsx` – allowed theme configuration.

Selected colors are applied immediately through root CSS variables:

`--t-bg`, `--t-text`, `--t-accent`, `--t-card`, `--t-muted`, `--t-border`

Additional transparent variants are generated for panels, borders, muted text and accent effects. The active theme is also exposed as `data-theme="light"` or `data-theme="dark"` on the document root.

## Persistence and safeguards

- Theme mode is stored in `localStorage` key `theme-mode`.
- Color palette is stored in `localStorage` key `theme-colors`.
- Page reload ke baad user ki last selection restore hoti hai.
- Agar saved theme branding ke allowed themes mein nahi hai, toh first allowed theme select hota hai.
- Light mode mein purana forced-white text/muted color automatically readable fallback se repair hota hai.
- Purane accent colors migrate hokar NMS red `#FF0015` ban jate hain.

## User flow

1. Top bar mein palette/theme icon select karein.
2. Required color ke liye swatch ya native color picker use karein.
3. Changes immediately poore interface mein reflect hote hain.
4. Defaults par lautne ke liye **Reset to Default** select karein.

