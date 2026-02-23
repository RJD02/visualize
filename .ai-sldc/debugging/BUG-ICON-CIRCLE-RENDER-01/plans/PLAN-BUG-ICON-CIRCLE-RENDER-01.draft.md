# PLAN-BUG-ICON-CIRCLE-RENDER-01.draft.md
# Debug Plan: Tech Icons Render as Blue Circles

## Entity ID
BUG-ICON-CIRCLE-RENDER-01

## Problem Understanding

Tech icons in the diagram viewer render as solid blue circles or simple blue geometric
shapes instead of their actual brand SVG logos (e.g. Kubernetes, Airflow, Postgres).

Evidence:
- evidence_1.png: "Kubernetes Cluster (PROD)" shows a small blue hexagon overlapping the "K"
- evidence_2.png: "Airflow/Superset/OpenMetadata" shows a LARGE blue circle overlapping "Ai"

## Root Cause Analysis (Confirmed by Code Inspection + Test)

### Root Cause 1 — `inline_use_references()` discards position/scale info (CRITICAL)

**Location**: `src/icons/inject.py` → `inline_use_references()`

**What happens**:
The server-side pipeline:
1. `inject_icons()` creates `<defs id="icon-sprite"><symbol id="icon-kubernetes" viewBox="0 0 128 128">...</symbol></defs>`
   and `<use href="#icon-kubernetes" x="-126" y="-10" width="20" height="20"/>` inside the node group.
2. `inline_use_references()` then replaces `<use href="#icon-kubernetes" x="-126" y="-10" width="20" height="20"/>`
   with `<g class="node-icon injected-icon" data-inlined-from="icon-kubernetes"><!-- paths --></g>`.

**The bug in `inline_use_references()`**:
The `<use>` element carries critical render attributes:
- `x`, `y` — position in the node's local coordinate space
- `width`, `height` — scale of the symbol viewBox content to desired size

When replaced with a `<g>`, these attributes are silently dropped. The brand icon paths
(e.g. Kubernetes paths in 0–128 coordinate space) are placed at (0,0) with no scaling.
In a Mermaid node centered at transform origin, (0,0) is the CENTER of the node.
128 SVG units extend far outside the 78-unit-tall node box, making the brand icon
essentially invisible (mispositioned and over-scaled, likely clipped).

**Verified by**:
```
python3 -c "from src.server import _auto_inject_icons; ..."
# data-icon-injected count: 17, data-inlined-from count: 17 after pipeline
# But brand paths at wrong coords — never visible in browser
```

### Root Cause 2 — Client-side icon injection uses circle-like placeholder paths

**Location**: `ui/src/diagram/iconRegistry.js` → `postProcessSvgWithIcons()`

**What happens**:
`window.ENABLE_SVG_ICON_INJECTION = true` is set in `App.jsx`.
`DiagramViewer.jsx` calls `postProcessSvgWithIcons(svgMarkup)` on every render.
`autoAssignIconsFromSvg()` scans all SVG text/foreignObject labels and injects
simple path icons from the `ICONS` object. These paths are placeholder shapes:

```js
airflow: { path: 'M2 12c0-5 4-9 9-9s9 4 9 9-4 9-9 9S2 17 2 12z' }  // literal circle!
kafka:   { path: 'M4 12a8 8 0 1116 0 8 8 0 01-16 0zm2 0h12' }        // circle with line
```

The `airflow` path traces a circle shape. With `.node-icon { fill: #1e40af }` (dark blue),
it renders as a large solid blue circle overlapping the node text.

**The client icon IS visible** because:
- It's positioned at `rx + 4, ry + (rh-20)/2` (correct left-edge position)
- It's inserted at `targetGroup.firstChild` (before the `<rect>`)
- SVG first-child renders BEHIND the rect, but the brand icon at inline position 2
  is invisible (wrong scale/coords), so only the client circle is visible

**No existing guard prevents double-injection**: the client does not check
`data-icon-injected="1"` before injecting.

## Proposed Fix

### Fix A — Remove `inline_use_references()` from the render pipeline

**File**: `src/server.py`

Remove the `inline_use_references()` call blocks in both render endpoints
(around lines 780 and 891). The `<use>` → `<symbol>` rendering works natively
in all modern browsers for inline SVG in HTML5. When the SVG is embedded
via `dangerouslySetInnerHTML`, the browser correctly scales and positions
`<use>` elements referencing `<symbol>` elements in `<defs>`.

Rationale: `inline_use_references()` was added to support SVG-as-`<img>`
embedding, where `<use>` refs to internal `<defs>` may not resolve. Our
pipeline embeds SVG inline (via `dangerouslySetInnerHTML`), so this
inlining step is unnecessary and actively harmful.

### Fix B — Guard client-side injection for server-already-injected nodes

**File**: `ui/src/diagram/iconRegistry.js` → `postProcessSvgWithIcons()`

Inside the `requests.forEach((req) => { ... })` loop, after `targetGroup`
is found, add:

```js
// Skip groups where server-side brand icon already injected
if (targetGroup.getAttribute('data-icon-injected') === '1') return;
```

This ensures the client-side circle paths are NEVER injected into nodes
that already have server-side brand icons, regardless of whether
`inline_use_references()` is used or not. Provides a safety layer.

## File-Level Change Scope

```
src/server.py
  - Remove inline_use_references() calls (~4 lines in 2 render endpoints)

ui/src/diagram/iconRegistry.js
  - Add data-icon-injected guard in postProcessSvgWithIcons() (~2 lines)
```

## Test Plan

### Unit Tests (Python)

**File**: `tests/unit/test_icon_injection_visibility.py`

Add test:
- `test_inline_not_called_in_pipeline`: verify that after `_auto_inject_icons()`,
  the SVG still contains `<use>` elements (not inlined), confirming we do NOT call
  `inline_use_references()` in the render path. (Structural test only.)
- `test_brand_icon_use_has_position`: verify injected `<use>` has x, y, width, height attrs.
- `test_no_circle_fallback_for_known_icon`: verify `inject_icons()` for "airflow" produces
  a `<symbol>` with actual `<path>` elements, NOT the generic circle path.

### Unit Tests (JS)

**File**: `tests/unit/icon_registry.test.js`

Add test:
- Confirm `postProcessSvgWithIcons()` skips nodes with `data-icon-injected="1"`.
  Create a minimal SVG with `data-icon-injected="1"` on a node group,
  run `postProcessSvgWithIcons()`, verify no `#fa_icon_` references are added to it.

### Playwright (E2E)

**File**: `tests/e2e/icon_presence.spec.js`

Update/extend existing spec:
- Navigate to the app and trigger a diagram render containing "Kubernetes Cluster"
  and "Airflow" nodes.
- Assert: SVG `<defs>` contains at least one `<symbol>` with `id` starting with `icon-`.
- Assert: `<use href="#icon-kubernetes">` exists and has `width`, `height`, `x`, `y` attributes.
- Assert: No node group has a `<use>` element referencing `#fa_icon_` (client-side circles).
- Take screenshot and save as evidence.

## Reproduction Automation Plan

Write `tests/e2e/bug_icon_circle_repro.spec.js`:
- Intentionally call `postProcessSvgWithIcons()` on a known SVG WITHOUT the guard
  (simulated regression)
- Confirm that WITHOUT the fix, `data-icon-injected` groups DO get circle injection
- Confirm that WITH the fix, they do NOT

## Risks

- Removing `inline_use_references()` may affect SVG-as-image downloads:
  If a user downloads the SVG and opens it in an SVG viewer that does not
  support `<use>` → `<symbol>` (rare, but possible in some old tools),
  icons would not appear. Risk is low given modern browser/tool support.
- Risk mitigated: `<use>` + `<symbol>` is standard SVG and supported by all
  major tools since 2015.

## Rollback Strategy

If fix causes regression: revert `src/server.py` by restoring the
`inline_use_references()` call, and instead fix `inline_use_references()` to
preserve position/scale via `transform="translate(x,y) scale(sx,sy)"`.

## Acceptance Summary

- Icons render as actual brand SVGs (not blue circles) in the UI
- At least Kubernetes and Airflow icons verified visually
- Server SVG has `<defs><symbol>` + `<use>` with position attributes
- Client does not double-inject simple paths over server icons
- All unit + Playwright tests pass
