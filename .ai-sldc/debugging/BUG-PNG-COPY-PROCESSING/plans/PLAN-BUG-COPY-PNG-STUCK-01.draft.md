# PLAN-BUG-COPY-PNG-STUCK-01
# Draft Plan — Fix "Copy PNG" Stuck in Processing State

**Entity ID:** BUG-PNG-COPY-PROCESSING
**Kind:** debug
**Branch:** feature/BUG-PNG-COPY-PROCESSING
**Plan ID:** PLAN-BUG-COPY-PNG-STUCK-01

---

## 1. Problem Understanding

Clicking "Copy PNG" in the DiagramViewer sets `busy=true` but the button never
returns to its normal state.  The user sees "Processing…" on the "Record GIF"
button (which shares the `busy` state) and all export buttons become disabled.

Screenshot evidence in bug reports shows the UI locked in this intermediate state.

---

## 2. Root Cause Analysis

### Primary: `exportSvgToPng()` Promise can hang indefinitely

Location: `ui/src/diagram/pngExport.js`

The function constructs a Promise whose only resolution paths are:
- `img.onload` → `canvas.toBlob()` callback → `resolve()` / `reject()`
- `img.onerror` → FileReader fallback → `resolve()` / `reject()`

**Hang vectors:**

| Vector | When | Effect |
|--------|------|--------|
| `canvas.toBlob()` callback never fires | Tainted canvas, browser GC race | Promise never resolves |
| `img.onload` never fires | SVG Blob URL blocked by browser policy | Promise never resolves |
| `img.onerror` never fires | Stalled network/resource loader (rare) | Promise never resolves |
| `FileReader.onload` stall | Large diagram, slow device | Long delay before fallback resolve |

There is **no timeout** on the outer Promise.  If any path stalls, `busy` stays
`true` forever because `setBusy(false)` only runs in `finally` (which only runs
after the Promise settles).

### Secondary: Clipboard API in non-secure or non-permitted context

`navigator.clipboard.write([item])` can:
- Throw immediately (not in secure context → `finally` fires → OK)
- Silently pend the permission dialog (user never acts → hangs after blob is ready)

In Cypress / test headless environments this often hangs silently.

### Tertiary: Shared `busy` state creates confusing UX

The same `busy` state is used by:
- `downloadPng()`
- `copyPngToClipboard()`
- `recordGif()`

When "Copy PNG" hangs, the "Record GIF" button label shows "Processing…"
(because that button reads `busy`), misleading the user.

### Code location

```
ui/src/diagram/DiagramViewer.jsx
  copyPngToClipboard()  lines 216-239  — no timeout, shared busy
  downloadPng()         lines 203-214  — shares busy

ui/src/diagram/pngExport.js
  exportSvgToPng()      lines 56-133   — no timeout, callback-only resolution
```

---

## 3. Proposed Fix

### Fix A — Add timeout to `exportSvgToPng()` (`pngExport.js`)

Wrap the existing Promise in a `Promise.race()` against a timeout:

```js
const EXPORT_TIMEOUT_MS = 10_000;

export function exportSvgToPng(svgMarkup, exportScale = 2) {
    const exportPromise = /* existing Promise body */;
    const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('PNG export timed out after 10s')), EXPORT_TIMEOUT_MS)
    );
    return Promise.race([exportPromise, timeoutPromise]);
}
```

This guarantees `exportSvgToPng` **always settles** within 10 seconds.
The `finally { setBusy(false) }` in `DiagramViewer.jsx` then fires unconditionally.

### Fix B — Separate per-button loading state (`DiagramViewer.jsx`)

Replace the single `busy` boolean with per-operation state:

```js
const [copyPngBusy, setCopyPngBusy] = useState(false);
const [downloadPngBusy, setDownloadPngBusy] = useState(false);
const [recordGifBusy, setRecordGifBusy] = useState(false);
```

- "Copy PNG" button: disabled and shows "Copying…" only when `copyPngBusy=true`
- "Download PNG": disabled when `downloadPngBusy=true`
- "Record GIF": disabled and shows "Processing…" only when `recordGifBusy=true`

This prevents one operation's stall from corrupting the label of an unrelated button.

### Fix C — Clipboard permission handling

After the PNG blob is ready:
1. If `navigator.clipboard.write` is available, wrap it in a timeout (e.g., 5s)
2. On timeout or failure, fall back to download + inform user via non-blocking
   UI status text (not `alert()`)

### Fix D — User-visible error display

Replace `alert()` calls with inline error text rendered in the component, styled
consistently with the existing error display pattern in `App.jsx`.

---

## 4. File-Level Change Scope

### MODIFIED files

| File | Change |
|------|--------|
| `ui/src/diagram/pngExport.js` | Add `Promise.race` timeout wrapper in `exportSvgToPng()` |
| `ui/src/diagram/DiagramViewer.jsx` | Separate per-button busy state; replace alert with inline error |

### NEW files

| File | Purpose |
|------|---------|
| `tests/e2e/bug_copy_png_regression.spec.js` | Playwright E2E: reproduce stuck state, verify fix |
| `tests/unit/test_png_export.spec.js` extended | JS unit test for timeout behavior |

### SDLC artifacts

| Path | Type |
|------|------|
| `.ai-sldc/debugging/BUG-PNG-COPY-PROCESSING/plans/PLAN-BUG-COPY-PNG-STUCK-01.draft.md` | This file |
| `.ai-sldc/debugging/BUG-PNG-COPY-PROCESSING/plans/PLAN-BUG-COPY-PNG-STUCK-01.locked.json` | On approval |
| `.ai-sldc/debugging/BUG-PNG-COPY-PROCESSING/logs/planning.log` |  |

---

## 5. Test Plan

### Execution Order

1. Unit tests: `npx vitest run tests/unit/test_png_export.spec.js`
2. Playwright E2E: `npx playwright test tests/e2e/bug_copy_png_regression.spec.js`

### Unit Tests (JS — `test_png_export.spec.js`)

| Test | Input | Expected |
|------|-------|---------|
| `test_export_resolves_within_timeout` | Valid small SVG | Promise resolves in < 5s |
| `test_export_rejects_on_timeout` | Mocked `canvas.toBlob` that never fires | Rejects with timeout error within 10.5s |
| `test_parseSvgDimensions_returns_fallback_for_null` | `null` | `null` |
| `test_parseSvgDimensions_reads_viewBox` | SVG with only viewBox | `{w, h}` from viewBox |

### Playwright E2E (`bug_copy_png_regression.spec.js`)

```
Pre-fix reproduction check (documented, then skipped after fix):
  - Open diagram page with pre-loaded SVG
  - Intercept canvas.toBlob to never fire (simulate stuck)
  - Click "Copy PNG"
  - Wait 11s
  - Assert button is NOT still disabled (timeout kicked in)
  - Assert error message visible in UI

Post-fix validation:
  - Open diagram page with valid SVG
  - Click "Copy PNG"
  - Wait for copyPngBusy to become false (max 12s)
  - Assert: no timeout error on valid SVG in standard browser
  - Assert: button re-enables within timeout window
  - Capture screenshot: BUG-PNG-COPY-PROCESSING-copy-png-success-<timestamp>.png
  - Assert: Download PNG still works
  - Assert: Export SVG / Copy SVG unaffected
```

### Evidence Collection

- Screenshot: `BUG-PNG-COPY-PROCESSING-processing-state-<timestamp>.png`
- Screenshot: `BUG-PNG-COPY-PROCESSING-success-outcome-<timestamp>.png`
- `run-meta.json` in `.ai-sldc/debugging/BUG-PNG-COPY-PROCESSING/evidence/ui/`

---

## 6. Acceptance Criteria Cross-Check

| Criterion | Implementation |
|-----------|---------------|
| Copy PNG completes or fails within 10s | `Promise.race` timeout in `exportSvgToPng` |
| Button state always resets after completion | `finally { setCopyPngBusy(false) }` per-button |
| Clear error message on failure | Inline UI error display (not alert) |
| Download PNG still works | Playwright regression assertion |
| Export SVG / Copy SVG unaffected | Playwright regression assertion |
| Playwright test reproduces stuck state | Mocked `toBlob` test case |
| Playwright test passes post-fix | Post-fix validation case |
| Unit tests pass | 4 JS unit tests |
| Confidence ≥ 0.85 | Review gate |

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| `Promise.race` timeout fires on slow/large diagrams that would have succeeded | 10s timeout is generous; user can retry; error message explains |
| Playwright cannot control `ClipboardItem` in headless browser | Test mocks clipboard API; also tests the fallback download path |
| Separate busy states increase component state complexity | Modest increase (3 booleans); well-contained |
| Inline error display styling inconsistency | Use same Tailwind classes as App.jsx error display |

---

## 8. Rollback Strategy

- `pngExport.js` change: Remove the `Promise.race` wrapper → revert to original.
- `DiagramViewer.jsx` change: Merge per-button states back to single `busy` → revert.

No database or IR schema changes.  All changes are frontend-only.

---

## 9. Out of Scope

- GIF recording (`recordGif`) is left with existing `busy` flag until a separate story covers it.
- Download PNG is not broken and does not need a timeout fix (it already works).
- Server-side PNG generation (not used; PNG is generated client-side via canvas).
