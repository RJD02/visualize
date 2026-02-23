# PLAN-STORY-DIAGRAM-VIEW-EXPORT-01 (Draft)

**Entity ID:** STORY-DIAGRAM-VIEW-EXPORT-01
**Kind:** feature
**Plan ID:** PLAN-STORY-DIAGRAM-VIEW-EXPORT-01
**Phase at creation:** planning
**Created:** 2026-02-23

---

## 1. Problem Understanding

### 1a. PNG Export Blur
Current `downloadPng` in `ui/src/diagram/DiagramViewer.jsx` uses `html2canvas`:
- Captures the live HTML element at `window.devicePixelRatio || 1` scale
- `html2canvas` rasterizes HTML DOM — performs poorly with inline SVG, embedded symbols, and `<use>` references (icons)
- The resulting PNG is pixel-for-pixel the CSS layout size, meaning on 96dpi screens it is a 1x raster
- Text, thin lines, and dense diagrams appear blurry when viewed at normal document zoom or printed

### 1b. No In-Canvas Zoom Controls
`DiagramViewer.jsx` renders the SVG directly via `dangerouslySetInnerHTML` with no scrollable/zoomable wrapper.
- Large diagrams overflow container bounds; user must resort to browser zoom (affects entire page)
- No zoom in/out, fit-to-view, or reset controls exist inside the diagram panel
- No pan/drag support when zoomed in

---

## 2. Proposed Fix

### 2a. Feature A — High-Quality PNG Export

**Approach:** Replace `html2canvas` with direct SVG → Canvas rasterization.

Pipeline:
1. Serialize processed SVG markup (with injected icons) to a Blob URL
2. Load into an `<img>` element
3. Create a `<canvas>` with dimensions `svgW * exportScale` × `svgH * exportScale`
4. Draw the image onto the canvas using `ctx.drawImage(img, 0, 0, canvasW, canvasH)`
5. Export via `canvas.toBlob('image/png')`

**Why this is better than html2canvas:**
- SVG is vector: scales to any resolution with zero quality loss
- Deterministic: same input SVG + same `exportScale` → identical PNG bytes
- No external library required at runtime (uses native browser Canvas API)
- Works fully offline (icons are already inlined as symbols)

**Export scale options:**
- Default: `2` (matches acceptance criterion ">=2x")
- UI allows user to select: 1x / 2x / 3x / 4x via a dropdown next to the Download PNG button

**SVG dimensions:** Read from `viewBox` attribute (preferred) or `width`/`height` attributes of the SVG root.

**Full diagram:** Export operates on the full SVG markup (not the scrolled/clipped container view).

**run-meta.json:** Store export scale, dimensions, and timestamp in evidence folder after each test export.

### 2b. Feature B — In-Canvas Zoom Controls

**Approach:** SVG viewBox manipulation + CSS overflow pan.

State:
```
zoom: float (default 1.0, min 0.1, max 10.0)
panX: float (SVG user-units, default 0)
panY: float (SVG user-units, default 0)
mode: 'fit' | 'manual'
```

The diagram SVG's `viewBox` attribute is recomputed on every zoom/pan state change:
```
viewBox = `${panX} ${panY} ${svgNativeW / zoom} ${svgNativeH / zoom}`
```

This approach:
- Keeps rendering fully vector (no pixelation)
- Requires zero CSS transform gymnastics
- Is compatible with icon `<use>` references and all SVG features
- Allows hit-testing to remain stable

**Controls to add (inside `.diagram-export-container` parent):**
- Zoom In (`+`): `zoom *= 1.25`
- Zoom Out (`-`): `zoom /= 1.25`
- Reset (`1:1`): `zoom = 1.0, panX = 0, panY = 0`
- Fit to View: compute `zoom = min(containerW / svgNativeW, containerH / svgNativeH) * 0.95`, center pan
- Maximize toggle: expand container to full viewport height via CSS class toggle

**Mouse wheel zoom:**
- `wheel` event on container: `zoom *= 1 + (-deltaY / 500)`; clamp to [0.1, 10.0]
- `event.preventDefault()` to suppress page scroll while hovering diagram

**Drag to pan:**
- `mousedown` on SVG: capture drag start in SVG user-unit coords
- `mousemove`: compute delta, update `panX`/`panY`
- `mouseup`: stop drag
- Cursor: `grab` at rest, `grabbing` during drag

**Maximize/Minimize:**
- Add `maximized` boolean state
- Toggle CSS class `diagram-maximized` on the wrapper div
- Add CSS: `.diagram-maximized { position: fixed; inset: 0; z-index: 9999; background: #0f172a; }`

---

## 3. File-Level Change Scope

| File | Change type | Description |
|------|-------------|-------------|
| `ui/src/diagram/DiagramViewer.jsx` | Modify | Add zoom state, viewBox manipulation, control bar, SVG→canvas export, maximize toggle |
| `ui/src/diagram/pngExport.js` | Create | Isolated pure function: `exportSvgToPng(svgMarkup, exportScale)` → Promise<Blob> |
| `tests/e2e/story03_export_zoom.spec.js` | Create | Playwright e2e: zoom controls interaction, PNG export, screenshot evidence |
| `tests/unit/test_png_export.js` | Create | Node unit test: canvas dimensions match `svgDim * scale`; deterministic output |
| `.ai-sldc/stories/story-03/evidence/ui/` | Populate | Screenshots, exported PNG, run-meta.json (during testing phase) |

**Files NOT modified:**
- `src/diagram/icon_injector.py` (no change to server-side injection)
- `src/server.py` (no change)
- Any other existing source files

---

## 4. Detailed Task Breakdown

### Task 1 — Create `pngExport.js`
```
ui/src/diagram/pngExport.js
```
- Export function `exportSvgToPng(svgMarkup, exportScale = 2)`
- Parse SVG to get `width`, `height`, `viewBox`
- Serialize SVG to Blob URL
- Draw to canvas at `w * exportScale` × `h * exportScale`
- Return `{ blob, width: canvasW, height: canvasH }`
- Fallback: if SVG has no explicit dimensions, default to 800×600

### Task 2 — Refactor `DiagramViewer.jsx`
A. Zoom state:
```javascript
const [zoom, setZoom] = useState(1.0);
const [panX, setPanX] = useState(0);
const [panY, setPanY] = useState(0);
const [maximized, setMaximized] = useState(false);
const [exportScale, setExportScale] = useState(2);
const svgNativeSize = useMemo(() => parseSvgDimensions(processedMarkup), [processedMarkup]);
```

B. Computed viewBox string (passed as prop to rendered SVG via DOM manipulation in useEffect):
```javascript
useEffect(() => {
  const svgEl = containerRef.current?.querySelector('svg');
  if (!svgEl || !svgNativeSize) return;
  const { w, h } = svgNativeSize;
  svgEl.setAttribute('viewBox', `${panX} ${panY} ${w / zoom} ${h / zoom}`);
  svgEl.setAttribute('width', '100%');
  svgEl.setAttribute('height', '100%');
}, [zoom, panX, panY, svgNativeSize]);
```

C. Fit-to-View:
```javascript
const fitToView = () => {
  const container = containerRef.current;
  if (!container || !svgNativeSize) return;
  const { w, h } = svgNativeSize;
  const cw = container.clientWidth;
  const ch = container.clientHeight;
  const newZoom = Math.min(cw / w, ch / h) * 0.95;
  setZoom(newZoom);
  setPanX(0); setPanY(0);
};
```

D. Replace `downloadPng` with SVG→canvas export:
```javascript
const downloadPng = async () => {
  const { blob } = await exportSvgToPng(processedMarkup, exportScale);
  downloadBlob(blob, 'diagram.png');
};
```

E. Zoom control bar (above the diagram canvas):
```jsx
<div className="zoom-controls flex gap-1 mb-1 items-center">
  <button onClick={() => setZoom(z => Math.min(z * 1.25, 10))} title="Zoom In">+</button>
  <button onClick={() => setZoom(z => Math.max(z / 1.25, 0.1))} title="Zoom Out">−</button>
  <button onClick={() => { setZoom(1); setPanX(0); setPanY(0); }} title="Reset">1:1</button>
  <button onClick={fitToView} title="Fit to View">Fit</button>
  <button onClick={() => setMaximized(m => !m)} title="Maximize">{maximized ? '⤡' : '⤢'}</button>
  <span className="text-xs ml-2">{Math.round(zoom * 100)}%</span>
</div>
```

F. Mouse wheel handler:
```javascript
const onWheel = (e) => {
  e.preventDefault();
  setZoom(z => Math.max(0.1, Math.min(10, z * (1 + (-e.deltaY / 500)))));
};
```

G. Drag to pan:
```javascript
const dragState = useRef(null);
const onMouseDown = (e) => {
  dragState.current = { startX: e.clientX, startY: e.clientY, px: panX, py: panY };
};
const onMouseMove = (e) => {
  if (!dragState.current || !svgNativeSize) return;
  const dx = (e.clientX - dragState.current.startX) / zoom * (svgNativeSize.w / containerRef.current.clientWidth);
  const dy = (e.clientY - dragState.current.startY) / zoom * (svgNativeSize.h / containerRef.current.clientHeight);
  setPanX(dragState.current.px - dx);
  setPanY(dragState.current.py - dy);
};
const onMouseUp = () => { dragState.current = null; };
```

### Task 3 — Playwright E2E Test
File: `tests/e2e/story03_export_zoom.spec.js`

Steps:
1. Navigate to `http://localhost:3000`
2. Submit diagram generation prompt (deterministic fixture prompt)
3. Wait for SVG to render (`[data-cy="diagram-viewer"] svg`)
4. Screenshot: baseline (before zoom)
5. Click Zoom In button 3 times → assert zoom label shows > 100%
6. Screenshot: zoomed in
7. Click Fit to View → assert diagram fills container
8. Screenshot: fit view
9. Click Reset → assert zoom label shows 100%
10. Export PNG (click Download PNG)
11. Verify PNG file downloaded (check via download event)
12. Save run-meta.json with scale and dimensions
13. Store all screenshots to `evidence/ui/screenshots/`

### Task 4 — Node Unit Test
File: `tests/unit/test_png_export.js`

Tests:
- `exportSvgToPng(svg, 2)` produces blob with correct canvas size (2x SVG dims)
- `exportSvgToPng(svg, 1)` produces blob with 1x SVG dims
- `exportSvgToPng(svg, 3)` produces blob with 3x SVG dims
- Deterministic: calling twice with same input produces blobs of same size

---

## 5. Acceptance Criteria Mapping

| Criterion | Implementation |
|-----------|----------------|
| A: PNG ≥ 2x sharper | SVG→canvas at `exportScale=2` by default |
| A: Uses explicit scale | `exportScale` state, defaults to 2 |
| A: Exports full diagram | Uses full `processedMarkup` SVG, not DOM screenshot |
| A: Preserves colors/icons/text | SVG is vector; icons are inlined symbols |
| A: No external network calls | Canvas API is native; SVG is local |
| A: Deterministic | Same SVG + same scale → same canvas dimensions |
| A: High Quality option | Default 2x; dropdown for 1x/2x/3x/4x |
| B: Zoom In/Out buttons | `+` / `−` buttons adjust zoom state |
| B: Reset button | `1:1` button sets zoom=1.0, pan=(0,0) |
| B: Fit to View | `Fit` button computes container-fill zoom |
| B: Does not affect page | viewBox manipulation scoped to SVG element only |
| B: Pan when zoomed | Drag-to-pan via mousedown/mousemove/mouseup |
| B: Diagram stays sharp during zoom | viewBox manipulation = pure vector scaling |
| B: Maximize/Minimize | Toggle `maximized` state → CSS fixed position |
| C: Playwright test | `tests/e2e/story03_export_zoom.spec.js` |
| C: Evidence screenshots | Saved to `evidence/ui/screenshots/` |
| C: Exported PNG stored | Saved to `evidence/ui/exports/` |
| C: run-meta.json | Written with scale + dimensions |
| D: No regression | Existing icon tests must still pass |
| D: Unit tests pass | `test_png_export.js` |
| D: Playwright pass | `story03_export_zoom.spec.js` |
| D: No new runtime deps | Only native Canvas API used |

---

## 6. Risks

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| SVG Blob URL CORS issue in some browsers | Low | Use `data:` URL instead of `createObjectURL` as fallback |
| SVG missing explicit width/height (uses viewBox only) | Medium | Parse `viewBox` fallback, default 800×600 if absent |
| Icon symbols not inlined when exporting (server-side SVG) | Low | `processedMarkup` already has inlined `<symbol>` + `<use>` |
| viewBox manipulation conflicts with SVG that uses fixed `width`/`height` | Medium | Remove `width`/`height` attrs when setting viewBox for zoom |
| Mouse wheel scroll conflict (user wants to scroll page) | Low | `preventDefault` only while cursor is inside diagram container |
| Maximize overlay covers other UI | Low | z-index management; add Escape key to exit maximize |
| Playwright download API differences by version | Low | Use `page.waitForEvent('download')` which is stable |

---

## 7. Rollback Strategy

- All changes are confined to `ui/src/diagram/DiagramViewer.jsx` and the new `pngExport.js`
- The existing `downloadSvg`, `copySvgToClipboard`, `recordGif` functions are untouched
- If PNG export regresses: the existing `html2canvas` fallback path can be re-enabled by reverting `pngExport.js` import
- Zoom state is local (React state); removing it reverts to current static view
- Git branch `feature/story-03-export-zoom` isolates all changes from `master`

---

## 8. Test Plan Summary

### Unit tests (Node/Jest, no server required)
- `tests/unit/test_png_export.js`: canvas size = SVG dims × scale; deterministic

### Playwright e2e (requires dev server at localhost:3000)
- `tests/e2e/story03_export_zoom.spec.js`
- Headless Chromium
- Captures screenshots before/after zoom + after export
- Stores evidence and run-meta.json

### Regression guard
- Existing `tests/e2e/icon_presence.spec.js` must still pass
- Existing Python unit tests (`tests/unit/test_icon_injector.py`) must still pass

---

## 9. Branch

`feature/story-03-export-zoom`

(Created during APPROVED phase, not planning phase.)

---

## Checksum

SHA256 of this plan file (computed at lock time).
