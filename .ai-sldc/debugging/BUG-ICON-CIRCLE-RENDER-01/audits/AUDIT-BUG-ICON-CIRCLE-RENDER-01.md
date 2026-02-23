# AUDIT-BUG-ICON-CIRCLE-RENDER-01
# Tech Icons Render as Blue Circles — Post-Fix Audit

## Summary of Changes

Two targeted fixes applied to eliminate blue circle rendering in place of brand logos.

### Fix 1 — `src/server.py`: Remove `inline_use_references()` from render pipeline

**Lines modified**: ~10 lines removed from each of two render endpoints.

The function `inline_use_references()` (in `src/icons/inject.py`) replaced `<use>` SVG
elements with plain `<g>` elements. The critical bug: it discarded `x`, `y`, `width`,
and `height` attributes from the `<use>` tags — the only mechanism by which the browser
would position and scale the icon content. Brand icon paths (e.g. 128×128 Kubernetes
paths) thus rendered at coordinate (0,0) in the node group's local space, at their
original scale, making them appear far outside the node bounds and invisible.

The fix removes the `inline_use_references()` call. Browsers render `<use>→<symbol>`
references natively and correctly for inline SVG embedded via `dangerouslySetInnerHTML`.
No inlining step is required for the inline-SVG embed pattern used by this application.

### Fix 2 — `ui/src/diagram/iconRegistry.js`: Add `data-icon-injected` guard

**Lines added**: 5-line guard block in `postProcessSvgWithIcons()`.

The client-side icon injection ran on every diagram render (because
`window.ENABLE_SVG_ICON_INJECTION = true`). It injected simplified geometric paths for
recognized service names, including a literal circle path for `airflow`:
```
'M2 12c0-5 4-9 9-9s9 4 9 9-4 9-9 9S2 17 2 12z'
```
With `fill: #1e40af` (dark blue), this renders as a solid blue circle overlapping text.

The fix adds a guard:
```js
if (targetGroup.getAttribute('data-icon-injected') === '1') return;
```
The attribute is set by the server-side pipeline (`inject_icons()`) to mark nodes that
already have brand icons. The guard prevents client-side circle injection on those nodes.

## Why Change Was Required

The server-side pipeline correctly reads real brand SVG files from `src/icons/`
(Apache-Airflow.svg, Kubernetes.svg, etc.) and embeds them as `<symbol>` elements in
`<defs>`. However, two defects prevented brand icons from appearing:

1. `inline_use_references()` destroyed position/scale → brand icons invisible
2. Client-side injection added placeholder circles → circles visible instead

Users saw: blue solid circles and simple polygons overlapping node label text.
Expected: recognizable brand logos (Kubernetes ship wheel, Airflow pinwheel, etc.)
positioned at the left edge of each node.

## Test Results

### Unit Tests (Python) — `pytest tests/unit/`
```
18 passed in 0.18s
```
New tests added:
- `test_inject_icons_use_has_position_attributes`: PASSED
- `test_brand_icon_symbol_contains_real_paths`: PASSED
- `test_data_icon_injected_flag_is_set`: PASSED
- `test_render_pipeline_leaves_use_intact`: PASSED

### Unit Tests (JS) — `node tests/unit/icon_registry.test.js`
```
4 passed
```
New test added:
- `client-side guard prevents double-injection`: PASSED

### Playwright E2E — `npx playwright test tests/e2e/`
```
63 passed in 19.0s
```
New tests added:
- `BUG-ICON-CIRCLE-RENDER-01: server pipeline emits <use> with position attributes`: PASSED
- `BUG-ICON-CIRCLE-RENDER-01: client guard prevents circle injection on server-injected nodes`: PASSED
No regressions in existing tests (icon_matrix: 50 pass, story03: 10 pass).

## Acceptance Checklist Verification

[x] Playwright test reproduces structural validation (use+symbol with position attrs)
[x] Evidence saved in: `.ai-sldc/debugging/BUG-ICON-CIRCLE-RENDER-01/evidence/`
[x] Snapshot of injected SVG with proper <symbol>+<use> structure saved:
    `.ai-sldc/debugging/BUG-ICON-CIRCLE-RENDER-01/evidence/snapshots/rendered.svg`
    - 2 symbols (kubernetes + airflow), 2 use elements, 11 real paths, 0 data-inlined-from

[x] Server SVG contains `<defs><symbol id="icon-kubernetes">` with real path elements
[x] `<use>` has x, y, width, height attributes (position/scale preserved)
[x] `data-icon-injected="1"` flag set on node groups
[x] No `<img src="...">` used for icons
[x] No runtime network requests for icons (all paths local to src/icons/)
[x] Same input SVG produces identical output (deterministic inject_icons())
[x] No external CDN dependency
[x] Unit test: inject_icons() returns SVG with real path elements for known icons
[x] Playwright test: no fa_icon_ placeholder injection on server-injected nodes
[x] All 18 Python unit tests pass
[x] All 63 Playwright tests pass headless

## Deviations from Plan

None. All tasks executed as planned.

## Evidence Directory

```
evidence/
  evidence_1.png  — original bug: small blue polygon on "Kubernetes Cluster (PROD)"
  evidence_2.png  — original bug: large blue circle on "Airflow/Superset/OpenMetadata"
  snapshots/
    rendered.svg  — fixed pipeline output: <symbol>+<use> with position attrs, 11 real paths
  ui/
    screenshots/
      BUG-ICON-CIRCLE-RENDER-01-icon-render.png   — Playwright test screenshot
      BUG-ICON-CIRCLE-RENDER-01-guard-test.png    — Playwright guard test screenshot
```

## Confidence Score

**0.95 / 1.0**

Factors:
- Root cause confirmed by code inspection and pipeline tracing (+)
- Both defects fixed with minimal, targeted changes (+)
- All 63 automated tests pass, no regressions (+)
- Rendered SVG evidence confirms <symbol>+<use> structure with real paths (+)
- Visual confirmation of fix requires browser with inline SVG support (standard) (+)
- Minor uncertainty: users who download SVGs and open in very old SVG viewers may not
  see icons (risk documented in plan, acceptable) (-)
