# STORY-DIAGRAM-VIEW-EXPORT-01
# Acceptance Criteria

## A) PNG Export Quality

[ ] Exported PNG is visibly sharper than current output for the same diagram (text and lines are readable).
[ ] Export uses explicit scale (default >= 2x) OR devicePixelRatio-aware scaling.
[ ] Exported PNG contains the full diagram (not cropped to viewport) by default.
[ ] Exported PNG preserves:
    - colors
    - icons (local SVG)
    - text layout
    - boundaries/containers
[ ] No external network calls are made during export (offline deterministic).
[ ] Export function is deterministic given same diagram + export settings.

### Export Settings
[ ] User can export at least one “High Quality” option (default).
[ ] (Optional) User can choose scale: 1x / 2x / 3x / 4x.

---

## B) In-Canvas Zoom / View Controls

Controls exist inside the diagram viewer box (not browser zoom):
[ ] Zoom In button increases diagram scale inside container.
[ ] Zoom Out button decreases diagram scale inside container.
[ ] Reset button returns to 100% zoom and default center.
[ ] Fit to View fits full diagram within container with reasonable padding.
[ ] Zoom does not affect the rest of the page (only diagram area).
[ ] When zoomed in, user can pan (drag to move view) OR equivalent interaction exists.
[ ] Diagram remains sharp during zoom (SVG scaling; no pixelated raster zoom).

### Maximize/Minimize (Viewer Only)
[ ] Maximize expands diagram viewer area (or full-screen) without changing browser zoom.
[ ] Minimize/Exit returns to normal layout.
[ ] State persists sensibly (zoom resets or preserves per spec; default: preserve).

---

## C) Automation Evidence (Mandatory)

[ ] Playwright (preferred) or Cypress headless test:
    - generates a diagram
    - uses zoom controls (zoom in/out + fit)
    - takes screenshot evidence
[ ] Export action produces PNG file and stores it under:
    .ai-sdlc/<kind>/<ENTITY-ID>/evidence/ui/exports/
[ ] Evidence includes:
    - at least 1 screenshot before zoom
    - at least 1 screenshot after zoom/fit
    - exported PNG file
    - run-meta.json with export scale and dimensions

---

## D) Regression Safety

[ ] Existing diagram rendering is not broken.
[ ] Existing icons and text still render correctly.
[ ] Unit tests pass.
[ ] Playwright/Cypress tests pass headless.
[ ] No new external dependencies at runtime (build-time deps allowed).

---

## Completion Gate

Story is complete when:
- All acceptance checks are satisfied
- Evidence artifacts exist and are referenced in audit
- PR review has zero open feedback
- Confidence score ≥ 0.85