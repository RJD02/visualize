# STORY-DIAGRAM-VIEW-EXPORT-01
# Crisp PNG Export + In-Canvas Zoom Controls for Diagram Viewer

## Objective

Improve diagram usability and shareability by:
1) Fixing PNG export quality (current exports are blurry).
2) Adding viewer controls to zoom in/out and fit/center the diagram inside the diagram container (without changing browser page zoom).

The goal is a professional, readable export and a usable viewing experience for large diagrams.

---

## Problem Statement

### PNG Export Blur
Current PNG exports are blurry, especially for:
- small text
- thin lines
- dense layouts
- large wide diagrams

Likely due to rasterization at low DPI/devicePixelRatio or exporting at CSS size instead of real pixel size.

### Poor Viewing Experience for Large Diagrams
Large diagrams exceed container width/height, and users currently rely on browser zoom or scrolling.
We need in-container zoom controls to:
- zoom in/out
- fit to screen
- reset to 100%
- optionally full-screen/maximize the diagram container

---

## Scope

### A) High-Quality PNG Export (Deterministic)
- Export should use high DPI rendering:
  - scale factor based on devicePixelRatio and/or explicit export scale (e.g., 2x/3x)
  - correct font rendering and line crispness
- Must export the **entire diagram** (not just visible viewport) unless user selects "export visible area" explicitly.
- Preserve visual fidelity:
  - colors
  - icons (inline SVG)
  - text layout
  - boundaries
- Deterministic output:
  - same input + same export settings → same PNG output
- No external network calls during export (icons are local).

### B) In-Canvas Zoom & View Controls (UI)
Add controls within the diagram viewer container:
- Zoom In
- Zoom Out
- Reset (100%)
- Fit to View
- Center / Pan-to-center (optional)
- Maximize/Minimize (optional full-screen container)

Zooming must:
- affect only diagram canvas/viewer region
- not modify global browser zoom
- keep text readable and avoid pixelation (prefer SVG scaling transforms)
- support mouse wheel + Ctrl/trackpad pinch (if feasible)
- allow panning when zoomed (drag to pan)

Implementation approach (preferred):
- Keep rendered diagram as SVG
- Apply transforms using viewBox manipulation or CSS transform with transform-origin and pan offsets
- Ensure hit-testing and interactions remain stable

---

## Non-Goals

- Not implementing a full diagram editor.
- Not implementing multi-page PDF export (separate story).
- Not implementing infinite canvas beyond zoom/pan.
- Not changing diagram generation/layout algorithm (unless required for export fidelity).

---

## Technical Notes / Expected Approach

### PNG Export
Preferred approach:
- Convert SVG → high-res PNG using a canvas at scaled resolution:
  - canvasWidth = diagramWidthPx * exportScale
  - canvasHeight = diagramHeightPx * exportScale
  - draw SVG onto canvas with proper scaling
- Ensure fonts are embedded/available, and SVG serialized correctly.
- Export scale options:
  - Default: 2x
  - Optional: 1x / 2x / 3x / 4x
- Export settings should be included in logs/audit and stored with run metadata.

### Zoom Controls
- Introduce a viewer state:
  - zoom (float, default 1.0)
  - panX, panY
  - mode: fit | manual
- Fit-to-view computes best zoom to fit diagram bounds within container with padding.
- Reset sets zoom=1, pan=(0,0).
- Maximize uses container full-screen (or expands panel) without affecting rest of page.

---

## Testing Strategy

### Unit
- PNG export function produces canvas size matching diagram bounds and chosen scale.
- Export uses deterministic scale logic (no random or CSS-dependent output).

### Playwright/Cypress UI (Preferred: Playwright for screenshots)
- Generate diagram in UI.
- Use zoom controls and take screenshots:
  - zoom in state differs from baseline
  - fit-to-view shows full diagram within container
- Export PNG and verify:
  - file exists
  - image dimensions reflect scale (>= base diagram pixel size)
  - visual clarity is improved (proxy checks: dimensions + non-empty + optional pixel/metadata check)
- Save screenshots/videos to entity evidence folder.

---

## Success Definition

- Exported PNG is crisp (text readable, lines sharp) at default scale.
- Viewer supports zoom in/out, reset, fit-to-view inside the diagram container.
- Users can inspect large diagrams without browser zooming.
- Tests pass and evidence (screenshots + exported PNG) is captured.