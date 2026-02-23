/**
 * pngExport.js — SVG to high-resolution PNG via native browser Canvas API.
 *
 * Replaces html2canvas for PNG export. Uses a vector-accurate pipeline:
 *   SVG markup → Blob URL → HTMLImageElement → canvas.drawImage at scale
 *
 * No external dependencies. Fully deterministic: same SVG + same exportScale
 * always produces the same canvas dimensions.
 *
 * story-03 / PLAN-STORY-DIAGRAM-VIEW-EXPORT-01
 */

/**
 * Parse native SVG width/height from markup string.
 *
 * Priority:
 *  1. width + height attributes (numeric, no units assumed to be user-units)
 *  2. viewBox third/fourth entries
 *  3. Fallback 800 × 600
 *
 * @param {string|null} svgMarkup
 * @returns {{ w: number, h: number }|null}
 */
export function parseSvgDimensions(svgMarkup) {
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
    } catch {
        return { w: 800, h: 600 };
    }
}

/**
 * Export SVG markup to a PNG Blob at the given scale factor.
 *
 * @param {string} svgMarkup  Full SVG string (with inlined icon symbols).
 * @param {number} exportScale  Multiplier applied to SVG native dimensions (default 2).
 * @returns {Promise<{ blob: Blob, width: number, height: number }>}
 */
export function exportSvgToPng(svgMarkup, exportScale = 2) {
    return new Promise((resolve, reject) => {
        const dims = parseSvgDimensions(svgMarkup);
        const nativeW = dims ? dims.w : 800;
        const nativeH = dims ? dims.h : 600;

        const canvasW = Math.round(nativeW * exportScale);
        const canvasH = Math.round(nativeH * exportScale);

        // Ensure the SVG has explicit width/height for correct canvas rendering.
        // Rewrite to add or replace the root svg attributes.
        let svgForExport = svgMarkup.replace(
            /(<svg\b[^>]*?)>/,
            (match, attrs) => {
                // Remove existing width/height so we can set exact values.
                const stripped = attrs.replace(/\s*(width|height)="[^"]*"/g, '');
                return `${stripped} width="${nativeW}" height="${nativeH}">`;
            }
        );

        const blob = new Blob([svgForExport], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(blob);

        const img = new Image();
        img.onload = () => {
            URL.revokeObjectURL(url);
            const canvas = document.createElement('canvas');
            canvas.width = canvasW;
            canvas.height = canvasH;
            const ctx = canvas.getContext('2d');
            // White background for legibility (PNG supports transparency, but white
            // is safer for documents / presentations)
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, canvasW, canvasH);
            ctx.drawImage(img, 0, 0, canvasW, canvasH);
            canvas.toBlob(
                (pngBlob) => {
                    if (pngBlob) {
                        resolve({ blob: pngBlob, width: canvasW, height: canvasH });
                    } else {
                        reject(new Error('canvas.toBlob returned null — canvas may be tainted'));
                    }
                },
                'image/png'
            );
        };
        img.onerror = () => {
            URL.revokeObjectURL(url);
            // Fallback: try data: URL if Blob URL fails (e.g., security policy)
            const reader = new FileReader();
            reader.onload = () => {
                const dataUrl = reader.result;
                const img2 = new Image();
                img2.onload = () => {
                    const canvas = document.createElement('canvas');
                    canvas.width = canvasW;
                    canvas.height = canvasH;
                    const ctx = canvas.getContext('2d');
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, canvasW, canvasH);
                    ctx.drawImage(img2, 0, 0, canvasW, canvasH);
                    canvas.toBlob(
                        (pngBlob) => {
                            if (pngBlob) resolve({ blob: pngBlob, width: canvasW, height: canvasH });
                            else reject(new Error('PNG export failed (both Blob URL and data URL approaches failed)'));
                        },
                        'image/png'
                    );
                };
                img2.onerror = () => reject(new Error('SVG image load failed with data URL fallback'));
                img2.src = dataUrl;
            };
            reader.onerror = () => reject(new Error('SVG Blob read failed'));
            reader.readAsDataURL(blob);
        };
        img.src = url;
    });
}
