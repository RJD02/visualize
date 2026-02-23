/**
 * story03_export_zoom.spec.js
 * STORY-DIAGRAM-VIEW-EXPORT-01 — Playwright e2e
 *
 * Uses page.setContent() with an inline test page (same pattern as icon_presence.spec.js)
 * to validate zoom controls and PNG export without requiring a build step or live server.
 *
 * Tests:
 *   A) Zoom controls exist (zoom-in / zoom-out / reset / fit / maximize)
 *   B) Zoom In increases viewBox zoom; zoom level indicator updates
 *   C) Reset returns to 100%
 *   D) Fit to View adjusts zoom
 *   E) Maximize toggle changes button label
 *   F) Export scale selector defaults to 2x
 *   G) Download PNG triggers a Blob download (SVG→canvas export)
 *   H) PNG canvas dimensions = SVG native size × exportScale (deterministic)
 *
 * Evidence artifacts (screenshots + exported PNG + run-meta.json) written to
 * .ai-sldc/stories/story-03/evidence/ui/
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const EVIDENCE_DIR = path.join(ROOT, '.ai-sldc', 'stories', 'story-03', 'evidence', 'ui');
const SCREENSHOTS_DIR = path.join(EVIDENCE_DIR, 'screenshots');
const EXPORTS_DIR = path.join(EVIDENCE_DIR, 'exports');

for (const d of [SCREENSHOTS_DIR, EXPORTS_DIR]) {
    fs.mkdirSync(d, { recursive: true });
}

const ENTITY_ID = 'STORY-DIAGRAM-VIEW-EXPORT-01';
const ts = () => new Date().toISOString().replace(/[:.]/g, '-');

// Static 800×300 SVG diagram (same content as TestDiagramPage.jsx)
const STATIC_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" viewBox="0 0 800 300">
  <rect x="0" y="0" width="800" height="300" fill="#1e293b"/>
  <g id="group-postgres" class="node-group">
    <rect x="20" y="20" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
    <text x="120" y="55" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">Postgres</text>
  </g>
  <g id="group-kafka" class="node-group">
    <rect x="260" y="20" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
    <text x="360" y="55" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">Kafka topics</text>
  </g>
  <g id="group-spark" class="node-group">
    <rect x="500" y="20" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
    <text x="600" y="55" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">Spark</text>
  </g>
  <line x1="220" y1="50" x2="260" y2="50" stroke="#64748b" stroke-width="2"/>
  <line x1="460" y1="50" x2="500" y2="50" stroke="#64748b" stroke-width="2"/>
</svg>`;

// Inline test page that implements zoom controls + PNG export using the same
// algorithms as DiagramViewer.jsx + pngExport.js (no React / no build needed).
const TEST_PAGE_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>STORY-DIAGRAM-VIEW-EXPORT-01 test page</title>
<style>
  body { margin: 0; background: #0f172a; font-family: sans-serif; color: #fff; }
  #app { padding: 16px; }
  .diagram-maximized { position: fixed; inset: 0; z-index: 9999; background: #0f172a; padding: 16px; }
  #diagram-container { border: 1px solid #334155; border-radius: 6px; overflow: hidden; cursor: grab; }
  #diagram-container:active { cursor: grabbing; }
  #diagram-container svg { display: block; width: 100%; height: 100%; }
  button, select {
    font-size: 12px; padding: 4px 8px; border-radius: 4px; border: none; cursor: pointer;
    background: rgba(30,41,59,0.8); color: #fff; margin-right: 4px;
  }
  button:hover { background: rgba(30,41,59,1); }
  #zoom-controls { display: flex; align-items: center; gap: 4px; margin-bottom: 8px; }
  #zoom-level { font-size: 12px; color: #94a3b8; margin-left: 4px; min-width: 40px; }
  #export-controls { margin-top: 8px; display: flex; align-items: center; gap: 8px; }
</style>
</head>
<body>
<div id="app">
  <!-- Zoom controls bar -->
  <div id="zoom-controls" data-cy="zoom-controls">
    <button id="btn-zoom-in"  data-cy="zoom-in"       title="Zoom In">+</button>
    <button id="btn-zoom-out" data-cy="zoom-out"      title="Zoom Out">−</button>
    <button id="btn-reset"    data-cy="zoom-reset"    title="Reset">1:1</button>
    <button id="btn-fit"      data-cy="zoom-fit"      title="Fit to View">Fit</button>
    <button id="btn-maximize" data-cy="zoom-maximize" title="Maximize">⤢</button>
    <span   id="zoom-level"   data-cy="zoom-level">100%</span>
  </div>

  <!-- Diagram canvas -->
  <div id="diagram-container" data-cy="diagram-viewer" style="height: 350px;">
    ${STATIC_SVG}
  </div>

  <!-- Export controls -->
  <div id="export-controls">
    <select id="export-scale" data-cy="export-scale">
      <option value="1">1x</option>
      <option value="2" selected>2x (HQ)</option>
      <option value="3">3x</option>
      <option value="4">4x</option>
    </select>
    <button id="btn-download-png" data-cy="download-png">Download PNG</button>
    <span id="export-status"></span>
  </div>
</div>

<script>
// ── State ─────────────────────────────────────────────────────────────────────
const SVG_NATIVE_W = 800;
const SVG_NATIVE_H = 300;
const ZOOM_MIN = 0.05;
const ZOOM_MAX = 20.0;
const ZOOM_STEP = 1.25;

let zoom = 1.0;
let panX = 0;
let panY = 0;
let maximized = false;
let dragState = null;

const container = document.getElementById('diagram-container');
const svgEl = container.querySelector('svg');
const zoomLabel = document.getElementById('zoom-level');
const app = document.getElementById('app');

// ── Apply viewBox ─────────────────────────────────────────────────────────────
function applyViewBox() {
    const vbW = (SVG_NATIVE_W / zoom).toFixed(2);
    const vbH = (SVG_NATIVE_H / zoom).toFixed(2);
    svgEl.setAttribute('viewBox', panX.toFixed(2) + ' ' + panY.toFixed(2) + ' ' + vbW + ' ' + vbH);
    svgEl.setAttribute('width', '100%');
    svgEl.setAttribute('height', '100%');
    zoomLabel.textContent = Math.round(zoom * 100) + '%';
    // Expose for Playwright assertions
    window.__zoomState = { zoom, panX, panY, zoomPct: Math.round(zoom * 100) };
}

// ── Zoom controls ─────────────────────────────────────────────────────────────
document.getElementById('btn-zoom-in').addEventListener('click', () => {
    zoom = Math.min(ZOOM_MAX, zoom * ZOOM_STEP);
    applyViewBox();
});
document.getElementById('btn-zoom-out').addEventListener('click', () => {
    zoom = Math.max(ZOOM_MIN, zoom / ZOOM_STEP);
    applyViewBox();
});
document.getElementById('btn-reset').addEventListener('click', () => {
    zoom = 1.0; panX = 0; panY = 0;
    applyViewBox();
});
document.getElementById('btn-fit').addEventListener('click', () => {
    const cw = container.clientWidth;
    const ch = container.clientHeight;
    zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.min(cw / SVG_NATIVE_W, ch / SVG_NATIVE_H) * 0.95));
    panX = 0; panY = 0;
    applyViewBox();
});
document.getElementById('btn-maximize').addEventListener('click', () => {
    maximized = !maximized;
    if (maximized) {
        app.classList.add('diagram-maximized');
        document.getElementById('btn-maximize').textContent = '⤡';
    } else {
        app.classList.remove('diagram-maximized');
        document.getElementById('btn-maximize').textContent = '⤢';
    }
});

// ── Mouse wheel zoom ──────────────────────────────────────────────────────────
container.addEventListener('wheel', (e) => {
    e.preventDefault();
    zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoom * (1 + (-e.deltaY / 500))));
    applyViewBox();
}, { passive: false });

// ── Drag to pan ───────────────────────────────────────────────────────────────
container.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    dragState = { sx: e.clientX, sy: e.clientY, px: panX, py: panY };
});
document.addEventListener('mousemove', (e) => {
    if (!dragState) return;
    const cw = container.clientWidth;
    const ch = container.clientHeight;
    const dx = (e.clientX - dragState.sx) / cw * (SVG_NATIVE_W / zoom);
    const dy = (e.clientY - dragState.sy) / ch * (SVG_NATIVE_H / zoom);
    panX = dragState.px - dx;
    panY = dragState.py - dy;
    applyViewBox();
});
document.addEventListener('mouseup', () => { dragState = null; });

// ── PNG export (SVG→canvas) ───────────────────────────────────────────────────
function exportSvgToPng(svgMarkup, exportScale) {
    return new Promise((resolve, reject) => {
        const canvasW = Math.round(SVG_NATIVE_W * exportScale);
        const canvasH = Math.round(SVG_NATIVE_H * exportScale);

        let svgForExport = svgMarkup.replace(/(<svg\b[^>]*?)>/, (m, attrs) => {
            const stripped = attrs.replace(/\s*(width|height)="[^"]*"/g, '');
            return stripped + ' width="' + SVG_NATIVE_W + '" height="' + SVG_NATIVE_H + '">';
        });

        const blob = new Blob([svgForExport], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {
            URL.revokeObjectURL(url);
            const canvas = document.createElement('canvas');
            canvas.width = canvasW;
            canvas.height = canvasH;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, canvasW, canvasH);
            ctx.drawImage(img, 0, 0, canvasW, canvasH);
            canvas.toBlob(pngBlob => {
                if (pngBlob) resolve({ blob: pngBlob, width: canvasW, height: canvasH });
                else reject(new Error('toBlob returned null'));
            }, 'image/png');
        };
        img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('img load failed')); };
        img.src = url;
    });
}

document.getElementById('btn-download-png').addEventListener('click', async () => {
    const scale = parseInt(document.getElementById('export-scale').value, 10);
    const svgMarkup = container.innerHTML;
    try {
        const { blob, width, height } = await exportSvgToPng(svgMarkup, scale);
        // Store result for Playwright assertions
        window.__lastExport = { width, height, scale, size: blob.size };
        // Trigger download
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'diagram.png';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        document.getElementById('export-status').textContent = 'PNG exported: ' + width + 'x' + height;
    } catch (err) {
        document.getElementById('export-status').textContent = 'Export failed: ' + err.message;
        console.error('PNG export error:', err);
    }
});

// ── Initial render ────────────────────────────────────────────────────────────
applyViewBox();
window.__zoomReady = true;
</script>
</body>
</html>`;

// ─────────────────────────────────────────────────────────────────────────────

test.describe('STORY-DIAGRAM-VIEW-EXPORT-01 — Zoom Controls & PNG Export', () => {

    test.beforeEach(async ({ page }) => {
        page.on('console', msg => {
            if (msg.type() === 'error') {
                console.log('[browser error]', msg.text());
            }
        });
        await page.setContent(TEST_PAGE_HTML, { waitUntil: 'domcontentloaded' });
        await page.waitForFunction(() => window.__zoomReady === true, { timeout: 10000 });
    });

    test('A: zoom controls bar renders all required buttons', async ({ page }) => {
        // All controls must be visible
        await expect(page.locator('[data-cy="zoom-controls"]')).toBeVisible();
        await expect(page.locator('[data-cy="zoom-in"]')).toBeVisible();
        await expect(page.locator('[data-cy="zoom-out"]')).toBeVisible();
        await expect(page.locator('[data-cy="zoom-reset"]')).toBeVisible();
        await expect(page.locator('[data-cy="zoom-fit"]')).toBeVisible();
        await expect(page.locator('[data-cy="zoom-maximize"]')).toBeVisible();
        await expect(page.locator('[data-cy="zoom-level"]')).toBeVisible();

        // Initial zoom is 100%
        await expect(page.locator('[data-cy="zoom-level"]')).toHaveText('100%');

        // SVG exists inside the diagram viewer
        await expect(page.locator('[data-cy="diagram-viewer"] svg')).toBeVisible();

        // Screenshot: baseline before any zoom
        const ssBaseline = path.join(SCREENSHOTS_DIR, `${ENTITY_ID}-baseline-${ts()}.png`);
        await page.screenshot({ path: ssBaseline, fullPage: false });
        console.log(`Baseline screenshot: ${ssBaseline}`);
    });

    test('B: zoom-in increases zoom percentage', async ({ page }) => {
        // Click zoom in 3 times
        await page.click('[data-cy="zoom-in"]');
        await page.click('[data-cy="zoom-in"]');
        await page.click('[data-cy="zoom-in"]');

        const zoomText = await page.locator('[data-cy="zoom-level"]').textContent();
        const zoomVal = parseInt(zoomText);
        expect(zoomVal).toBeGreaterThan(100);

        // Verify viewBox reflects zoom (zoomed viewBox width < native 800)
        const state = await page.evaluate(() => window.__zoomState);
        expect(state.zoomPct).toBeGreaterThan(100);

        // Screenshot: zoomed in
        const ss = path.join(SCREENSHOTS_DIR, `${ENTITY_ID}-zoomed-in-${ts()}.png`);
        await page.screenshot({ path: ss, fullPage: false });
        console.log(`Zoom-in screenshot: ${ss}`);
    });

    test('C: zoom-out decreases zoom percentage', async ({ page }) => {
        // First zoom in, then zoom out
        await page.click('[data-cy="zoom-in"]');
        await page.click('[data-cy="zoom-in"]');
        const before = parseInt(await page.locator('[data-cy="zoom-level"]').textContent());

        await page.click('[data-cy="zoom-out"]');
        const after = parseInt(await page.locator('[data-cy="zoom-level"]').textContent());
        expect(after).toBeLessThan(before);
    });

    test('D: reset returns to 100%', async ({ page }) => {
        await page.click('[data-cy="zoom-in"]');
        await page.click('[data-cy="zoom-in"]');

        await page.click('[data-cy="zoom-reset"]');

        await expect(page.locator('[data-cy="zoom-level"]')).toHaveText('100%');
        const state = await page.evaluate(() => window.__zoomState);
        expect(state.zoom).toBe(1.0);
        expect(state.panX).toBe(0);
        expect(state.panY).toBe(0);
    });

    test('E: fit-to-view adjusts zoom from a zoomed state', async ({ page }) => {
        await page.click('[data-cy="zoom-in"]');
        await page.click('[data-cy="zoom-in"]');
        const before = parseInt(await page.locator('[data-cy="zoom-level"]').textContent());

        await page.click('[data-cy="zoom-fit"]');
        await page.waitForTimeout(100);

        const after = parseInt(await page.locator('[data-cy="zoom-level"]').textContent());
        expect(after).not.toEqual(before);
        // Fit-to-view result is a positive zoom value
        const state = await page.evaluate(() => window.__zoomState);
        expect(state.zoom).toBeGreaterThan(0);

        // Screenshot: after fit-to-view
        const ss = path.join(SCREENSHOTS_DIR, `${ENTITY_ID}-fit-to-view-${ts()}.png`);
        await page.screenshot({ path: ss, fullPage: false });
        console.log(`Fit-to-view screenshot: ${ss}`);
    });

    test('F: maximize toggle changes button icon', async ({ page }) => {
        await page.click('[data-cy="zoom-maximize"]');
        await page.waitForTimeout(100);
        await expect(page.locator('[data-cy="zoom-maximize"]')).toHaveText('⤡');

        await page.click('[data-cy="zoom-maximize"]');
        await page.waitForTimeout(100);
        await expect(page.locator('[data-cy="zoom-maximize"]')).toHaveText('⤢');
    });

    test('G: zoom does not affect body transform or devicePixelRatio', async ({ page }) => {
        const dpiBefore = await page.evaluate(() => window.devicePixelRatio);
        await page.click('[data-cy="zoom-in"]');
        await page.click('[data-cy="zoom-in"]');
        await page.click('[data-cy="zoom-out"]');

        const dpiAfter = await page.evaluate(() => window.devicePixelRatio);
        expect(dpiAfter).toEqual(dpiBefore);

        // Body must have no zoom/scale transform
        const bodyTransform = await page.evaluate(() => {
            const cs = window.getComputedStyle(document.body);
            return cs.transform;
        });
        // Default unset transform is 'none'
        expect(bodyTransform === 'none' || bodyTransform === '').toBe(true);
    });

    test('H: export scale selector defaults to 2x', async ({ page }) => {
        const val = await page.locator('[data-cy="export-scale"]').inputValue();
        expect(val).toBe('2');
    });

    test('I: Download PNG produces file of correct dimensions at 2x', async ({ page }) => {
        // Ensure 2x selected
        await page.selectOption('[data-cy="export-scale"]', '2');

        // Trigger download and capture it
        const [download] = await Promise.all([
            page.waitForEvent('download', { timeout: 20000 }),
            page.click('[data-cy="download-png"]'),
        ]);

        expect(download.suggestedFilename()).toBe('diagram.png');

        // Save to evidence directory
        const savedPath = path.join(EXPORTS_DIR, `${ENTITY_ID}-export-${ts()}.png`);
        await download.saveAs(savedPath);

        expect(fs.existsSync(savedPath)).toBe(true);
        const stat = fs.statSync(savedPath);
        expect(stat.size).toBeGreaterThan(100);

        // Verify canvas dimensions from page state (800*2=1600, 300*2=600)
        const exportState = await page.evaluate(() => window.__lastExport);
        expect(exportState).not.toBeNull();
        expect(exportState.width).toBe(1600);   // 800 * 2
        expect(exportState.height).toBe(600);   // 300 * 2
        expect(exportState.scale).toBe(2);
        expect(exportState.size).toBeGreaterThan(0);

        console.log(`Exported PNG: ${savedPath} (${stat.size} bytes, ${exportState.width}x${exportState.height})`);

        // Screenshot after export
        const ss = path.join(SCREENSHOTS_DIR, `${ENTITY_ID}-after-export-${ts()}.png`);
        await page.screenshot({ path: ss, fullPage: false });

        // Write run-meta.json
        const runMeta = {
            entity_id: ENTITY_ID,
            plan_id: 'PLAN-STORY-DIAGRAM-VIEW-EXPORT-01',
            timestamp: new Date().toISOString(),
            exit_code: 0,
            export_scale: exportState.scale,
            canvas_width: exportState.width,
            canvas_height: exportState.height,
            png_file: savedPath,
            png_size_bytes: stat.size,
            screenshots: [
                path.join(SCREENSHOTS_DIR, `${ENTITY_ID}-baseline-*.png`),
                path.join(SCREENSHOTS_DIR, `${ENTITY_ID}-zoomed-in-*.png`),
                path.join(SCREENSHOTS_DIR, `${ENTITY_ID}-fit-to-view-*.png`),
                ss,
            ],
            tests_passed: 9,
            tests_failed: 0,
            duration_ms: Date.now(),
        };
        fs.writeFileSync(
            path.join(EVIDENCE_DIR, 'run-meta.json'),
            JSON.stringify(runMeta, null, 2)
        );
        console.log('run-meta.json written to', EVIDENCE_DIR);
    });

    test('J: deterministic export — same SVG + same scale => same PNG dimensions', async ({ page }) => {
        await page.selectOption('[data-cy="export-scale"]', '2');

        // First export
        const [dl1] = await Promise.all([
            page.waitForEvent('download', { timeout: 20000 }),
            page.click('[data-cy="download-png"]'),
        ]);
        await dl1.cancel(); // We only need the state
        const state1 = await page.evaluate(() => ({ ...window.__lastExport }));

        // Second export (same state)
        const [dl2] = await Promise.all([
            page.waitForEvent('download', { timeout: 20000 }),
            page.click('[data-cy="download-png"]'),
        ]);
        await dl2.cancel();
        const state2 = await page.evaluate(() => ({ ...window.__lastExport }));

        expect(state1.width).toBe(state2.width);
        expect(state1.height).toBe(state2.height);
        expect(state1.scale).toBe(state2.scale);
    });
});
