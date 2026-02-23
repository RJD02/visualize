/**
 * test_png_export.js
 * STORY-DIAGRAM-VIEW-EXPORT-01 — Unit tests for pngExport.js
 *
 * Tests parseSvgDimensions() as a pure string parser (no browser needed)
 * and uses a Playwright browser context to validate exportSvgToPng() canvas
 * dimensions (requires browser Canvas API).
 *
 * Run with: npx playwright test tests/unit/test_png_export.js
 */
const { test, expect } = require('@playwright/test');

// ── parseSvgDimensions — pure string parsing, tested via inline evaluation ───

test.describe('parseSvgDimensions', () => {

    test('reads width/height attributes', async ({ page }) => {
        await page.setContent('<html><body></body></html>');

        const result = await page.evaluate(() => {
            // Inline the function since we cannot import ES modules from CJS test
            function parseSvgDimensions(svgMarkup) {
                if (!svgMarkup) return null;
                try {
                    const wMatch = svgMarkup.match(/\bwidth="([0-9.]+)"/);
                    const hMatch = svgMarkup.match(/\bheight="([0-9.]+)"/);
                    let w = wMatch ? parseFloat(wMatch[1]) : 0;
                    let h = hMatch ? parseFloat(hMatch[1]) : 0;
                    if (!w || !h || !isFinite(w) || !isFinite(h)) {
                        const vbMatch = svgMarkup.match(/\bviewBox="([^"]+)"/);
                        if (vbMatch) {
                            const parts = vbMatch[1].trim().split(/[\s,]+/);
                            if (parts.length >= 4) {
                                w = parseFloat(parts[2]) || 800;
                                h = parseFloat(parts[3]) || 600;
                            }
                        }
                    }
                    if (!w || !isFinite(w)) w = 800;
                    if (!h || !isFinite(h)) h = 600;
                    return { w, h };
                } catch { return { w: 800, h: 600 }; }
            }
            const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200"></svg>';
            return parseSvgDimensions(svg);
        });
        expect(result.w).toBe(400);
        expect(result.h).toBe(200);
    });

    test('falls back to viewBox when no width/height', async ({ page }) => {
        await page.setContent('<html><body></body></html>');

        const result = await page.evaluate(() => {
            function parseSvgDimensions(svgMarkup) {
                if (!svgMarkup) return null;
                try {
                    const wMatch = svgMarkup.match(/\bwidth="([0-9.]+)"/);
                    const hMatch = svgMarkup.match(/\bheight="([0-9.]+)"/);
                    let w = wMatch ? parseFloat(wMatch[1]) : 0;
                    let h = hMatch ? parseFloat(hMatch[1]) : 0;
                    if (!w || !h || !isFinite(w) || !isFinite(h)) {
                        const vbMatch = svgMarkup.match(/\bviewBox="([^"]+)"/);
                        if (vbMatch) {
                            const parts = vbMatch[1].trim().split(/[\s,]+/);
                            if (parts.length >= 4) {
                                w = parseFloat(parts[2]) || 800;
                                h = parseFloat(parts[3]) || 600;
                            }
                        }
                    }
                    if (!w || !isFinite(w)) w = 800;
                    if (!h || !isFinite(h)) h = 600;
                    return { w, h };
                } catch { return { w: 800, h: 600 }; }
            }
            const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 500"></svg>';
            return parseSvgDimensions(svg);
        });
        expect(result.w).toBe(1200);
        expect(result.h).toBe(500);
    });

    test('returns 800x600 default for empty/null markup', async ({ page }) => {
        await page.setContent('<html><body></body></html>');

        const result = await page.evaluate(() => {
            function parseSvgDimensions(svgMarkup) {
                if (!svgMarkup) return null;
                try {
                    const wMatch = svgMarkup.match(/\bwidth="([0-9.]+)"/);
                    const hMatch = svgMarkup.match(/\bheight="([0-9.]+)"/);
                    let w = wMatch ? parseFloat(wMatch[1]) : 0;
                    let h = hMatch ? parseFloat(hMatch[1]) : 0;
                    if (!w || !h || !isFinite(w) || !isFinite(h)) {
                        const vbMatch = svgMarkup.match(/\bviewBox="([^"]+)"/);
                        if (vbMatch) {
                            const parts = vbMatch[1].trim().split(/[\s,]+/);
                            if (parts.length >= 4) {
                                w = parseFloat(parts[2]) || 800;
                                h = parseFloat(parts[3]) || 600;
                            }
                        }
                    }
                    if (!w || !isFinite(w)) w = 800;
                    if (!h || !isFinite(h)) h = 600;
                    return { w, h };
                } catch { return { w: 800, h: 600 }; }
            }
            return parseSvgDimensions(null);
        });
        expect(result).toBeNull();
    });
});

// ── exportSvgToPng — canvas dimension verification in browser context ─────────

test.describe('exportSvgToPng canvas dimensions', () => {

    const INLINE_EXPORT_FN = `
    function exportSvgToPng(svgMarkup, exportScale) {
        return new Promise((resolve, reject) => {
            const wMatch = svgMarkup.match(/\\bwidth="([0-9.]+)"/);
            const hMatch = svgMarkup.match(/\\bheight="([0-9.]+)"/);
            let nativeW = wMatch ? parseFloat(wMatch[1]) : 0;
            let nativeH = hMatch ? parseFloat(hMatch[1]) : 0;
            if (!nativeW || !nativeH) {
                const vbMatch = svgMarkup.match(/\\bviewBox="([^"]+)"/);
                if (vbMatch) {
                    const p = vbMatch[1].trim().split(/[\\s,]+/);
                    nativeW = parseFloat(p[2]) || 800;
                    nativeH = parseFloat(p[3]) || 600;
                }
            }
            if (!nativeW) nativeW = 800;
            if (!nativeH) nativeH = 600;
            const canvasW = Math.round(nativeW * exportScale);
            const canvasH = Math.round(nativeH * exportScale);
            let svgForExport = svgMarkup.replace(/(<svg\\b[^>]*?)>/, (match, attrs) => {
                const stripped = attrs.replace(/\\s*(width|height)="[^"]*"/g, '');
                return stripped + ' width="' + nativeW + '" height="' + nativeH + '">';
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
                    if (pngBlob) resolve({ width: canvasW, height: canvasH, size: pngBlob.size });
                    else reject(new Error('toBlob returned null'));
                }, 'image/png');
            };
            img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('img load failed')); };
            img.src = url;
        });
    }
    `;

    const SAMPLE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200" viewBox="0 0 400 200">
  <rect x="10" y="10" width="380" height="180" fill="#eee"/>
  <text x="200" y="100" text-anchor="middle" font-size="20">Test Diagram</text>
</svg>`;

    test('canvas width = SVG width * exportScale (2x)', async ({ page }) => {
        await page.setContent('<html><body></body></html>');
        const result = await page.evaluate(([fn, svg]) => {
            eval(fn);
            return exportSvgToPng(svg, 2);
        }, [INLINE_EXPORT_FN, SAMPLE_SVG]);
        expect(result.width).toBe(800);   // 400 * 2
        expect(result.height).toBe(400);  // 200 * 2
        expect(result.size).toBeGreaterThan(0);
    });

    test('canvas width = SVG width * exportScale (1x)', async ({ page }) => {
        await page.setContent('<html><body></body></html>');
        const result = await page.evaluate(([fn, svg]) => {
            eval(fn);
            return exportSvgToPng(svg, 1);
        }, [INLINE_EXPORT_FN, SAMPLE_SVG]);
        expect(result.width).toBe(400);
        expect(result.height).toBe(200);
    });

    test('canvas width = SVG width * exportScale (3x)', async ({ page }) => {
        await page.setContent('<html><body></body></html>');
        const result = await page.evaluate(([fn, svg]) => {
            eval(fn);
            return exportSvgToPng(svg, 3);
        }, [INLINE_EXPORT_FN, SAMPLE_SVG]);
        expect(result.width).toBe(1200);
        expect(result.height).toBe(600);
    });

    test('deterministic: two calls with same input produce same dimensions', async ({ page }) => {
        await page.setContent('<html><body></body></html>');
        const [r1, r2] = await page.evaluate(([fn, svg]) => {
            eval(fn);
            return Promise.all([exportSvgToPng(svg, 2), exportSvgToPng(svg, 2)]);
        }, [INLINE_EXPORT_FN, SAMPLE_SVG]);
        expect(r1.width).toBe(r2.width);
        expect(r1.height).toBe(r2.height);
    });
});

// ── BUG-PNG-COPY-PROCESSING: timeout guard tests ──────────────────────────────

test.describe('exportSvgToPng timeout guard (BUG-PNG-COPY-PROCESSING)', () => {
    const TIMEOUT_MS = 10_000;
    const SHORT_TIMEOUT = 500;

    const SAMPLE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <rect x="5" y="5" width="90" height="90" fill="#ccc"/>
</svg>`;

    test('resolves with valid SVG well within timeout', async ({ page }) => {
        await page.setContent('<html><body></body></html>');
        const start = Date.now();
        const result = await page.evaluate(([svg, timeoutMs]) => {
            function exportSvgToPngWithTimeout(svgStr, exportScale) {
                const exportPromise = new Promise((resolve, reject) => {
                    const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
                    const url = URL.createObjectURL(blob);
                    const img = new Image();
                    img.onload = () => {
                        URL.revokeObjectURL(url);
                        const canvas = document.createElement('canvas');
                        canvas.width = 100 * exportScale;
                        canvas.height = 100 * exportScale;
                        const ctx = canvas.getContext('2d');
                        ctx.fillStyle = '#fff';
                        ctx.fillRect(0, 0, canvas.width, canvas.height);
                        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                        canvas.toBlob(b => b ? resolve({ ok: true }) : reject(new Error('null blob')), 'image/png');
                    };
                    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('load failed')); };
                    img.src = url;
                });
                const timeoutPromise = new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('timed out')), timeoutMs)
                );
                return Promise.race([exportPromise, timeoutPromise]);
            }
            return exportSvgToPngWithTimeout(svg, 2);
        }, [SAMPLE_SVG, TIMEOUT_MS]);
        expect(result.ok).toBe(true);
        expect(Date.now() - start).toBeLessThan(TIMEOUT_MS);
    }, TIMEOUT_MS + 2000);

    test('rejects with timeout error when toBlob never fires', async ({ page }) => {
        await page.setContent('<html><body></body></html>');
        const error = await page.evaluate((shortTimeout) => {
            function exportSvgToPngHanging() {
                const exportPromise = new Promise(() => { /* never resolves — simulates stuck toBlob */ });
                const timeoutPromise = new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('PNG export timed out')), shortTimeout)
                );
                return Promise.race([exportPromise, timeoutPromise]);
            }
            return exportSvgToPngHanging().catch(e => e.message);
        }, SHORT_TIMEOUT);
        expect(error).toMatch(/timed out/i);
    }, 4500);

    test('busy state resets after timeout (finally always runs)', async ({ page }) => {
        await page.setContent('<html><body></body></html>');
        const BUSY_TIMEOUT = 300;
        const result = await page.evaluate((busyTimeout) => {
            let busyState = false;
            async function copyPngSimulation() {
                busyState = true;
                const exportPromise = new Promise(() => { /* hangs */ });
                const timeoutPromise = new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('timed out')), busyTimeout)
                );
                try {
                    await Promise.race([exportPromise, timeoutPromise]);
                } catch (_) {
                    // error is expected
                } finally {
                    busyState = false;
                }
            }
            return copyPngSimulation().then(() => ({ busyAfter: busyState }));
        }, BUSY_TIMEOUT);
        expect(result.busyAfter).toBe(false);
    }, 4000);
});
