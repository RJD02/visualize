/**
 * DiagramViewer.jsx
 *
 * story-03 (STORY-DIAGRAM-VIEW-EXPORT-01):
 *   - High-quality PNG export via SVG→canvas (replaces html2canvas).
 *   - In-canvas zoom / pan controls (viewBox manipulation — fully vector, no pixelation).
 *   - Maximize/minimize toggle.
 */
import { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { postProcessSvgWithIcons } from './iconRegistry.js';
import { exportSvgToPng, parseSvgDimensions } from './pngExport.js';

const ZOOM_MIN = 0.05;
const ZOOM_MAX = 20.0;
const ZOOM_STEP = 1.25;

const BTN = 'text-xs px-2 py-1 rounded bg-slate-800/60 hover:bg-slate-800/80 select-none';
const BTN_ACTIVE = 'text-xs px-2 py-1 rounded bg-indigo-700 hover:bg-indigo-600 text-white select-none';

export default function DiagramViewer({ svgMarkup, className = '', onBlockSelect, dataCy }) {
    const containerRef = useRef(null);

    // ── export ────────────────────────────────────────────────────────────────
    const [busy, setBusy] = useState(false);
    const [exportScale, setExportScale] = useState(2);

    // ── zoom / pan ─────────────────────────────────────────────────────────────
    const [zoom, setZoom] = useState(1.0);
    const [panX, setPanX] = useState(0);
    const [panY, setPanY] = useState(0);
    const [maximized, setMaximized] = useState(false);
    const dragRef = useRef(null);

    // ── processed markup (icon injection) ────────────────────────────────────
    const processedMarkup = useMemo(() => {
        try {
            if (typeof window !== 'undefined' && window.ENABLE_SVG_ICON_INJECTION && svgMarkup && svgMarkup.includes('<svg')) {
                return postProcessSvgWithIcons(svgMarkup);
            }
        } catch (_) {}
        return svgMarkup;
    }, [svgMarkup]);

    // ── native SVG dimensions (for viewBox arithmetic) ────────────────────────
    const svgNativeSize = useMemo(() => parseSvgDimensions(processedMarkup), [processedMarkup]);

    // Reset zoom/pan when a new diagram loads
    useEffect(() => {
        setZoom(1.0);
        setPanX(0);
        setPanY(0);
    }, [processedMarkup]);

    // Apply zoom+pan by rewriting the SVG viewBox after every render
    useEffect(() => {
        try {
            const svgEl = containerRef.current?.querySelector('svg');
            if (!svgEl || !svgNativeSize) return;
            const { w, h } = svgNativeSize;
            const vbW = (w / zoom).toFixed(2);
            const vbH = (h / zoom).toFixed(2);
            svgEl.setAttribute('viewBox', `${panX.toFixed(2)} ${panY.toFixed(2)} ${vbW} ${vbH}`);
            // Make SVG fill its container while respecting its aspect ratio
            svgEl.setAttribute('width', '100%');
            svgEl.setAttribute('height', '100%');
            svgEl.style.display = 'block';
        } catch (_) {}
    }, [zoom, panX, panY, svgNativeSize, processedMarkup]);

    // Debug effect — detect render mode, expose for tests
    useEffect(() => {
        try {
            const debug = typeof window !== 'undefined' && window.DEBUG_SVG_RENDER;
            const root = containerRef.current;
            if (!root) return;
            const child = root.firstElementChild;
            const hasSvgDesc = !!root.querySelector('svg');
            let mode = 'unknown';
            if (child) {
                const tn = child.tagName && child.tagName.toLowerCase();
                if (tn === 'svg' || hasSvgDesc) mode = 'inline';
                else if (tn === 'img' || tn === 'object' || tn === 'embed' || tn === 'iframe') mode = 'img';
            } else if (hasSvgDesc) mode = 'inline';
            if (debug) {
                try {
                    console.debug('diagramRenderDebug', { rendering_mode: mode, childTag: child && child.tagName, hasSvgDesc });
                    window.__diagramRenderDebug = { rendering_mode: mode, childTag: child && child.tagName, hasSvgDesc };
                    root.setAttribute('data-testid', 'diagram-root');
                } catch (_) {}
            }
        } catch (_) {}
    }, [processedMarkup]);

    // ── zoom callbacks ─────────────────────────────────────────────────────────
    const zoomIn = useCallback(() => setZoom(z => Math.min(ZOOM_MAX, z * ZOOM_STEP)), []);
    const zoomOut = useCallback(() => setZoom(z => Math.max(ZOOM_MIN, z / ZOOM_STEP)), []);
    const resetZoom = useCallback(() => { setZoom(1.0); setPanX(0); setPanY(0); }, []);

    const fitToView = useCallback(() => {
        const container = containerRef.current;
        if (!container || !svgNativeSize) return;
        const { w, h } = svgNativeSize;
        const cw = container.clientWidth || w;
        const ch = container.clientHeight || h;
        if (!cw || !ch) return;
        const newZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.min(cw / w, ch / h) * 0.95));
        setZoom(newZoom);
        setPanX(0);
        setPanY(0);
    }, [svgNativeSize]);

    // ── mouse wheel zoom ───────────────────────────────────────────────────────
    const onWheel = useCallback((e) => {
        e.preventDefault();
        const delta = -e.deltaY;
        setZoom(z => Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z * (1 + delta / 500))));
    }, []);

    // Attach wheel listener with { passive: false } so preventDefault works
    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        el.addEventListener('wheel', onWheel, { passive: false });
        return () => el.removeEventListener('wheel', onWheel);
    }, [onWheel, processedMarkup]);

    // ── drag-to-pan ────────────────────────────────────────────────────────────
    const onMouseDown = useCallback((e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        dragRef.current = { startX: e.clientX, startY: e.clientY, px: panX, py: panY };
    }, [panX, panY]);

    const onMouseMove = useCallback((e) => {
        if (!dragRef.current || !svgNativeSize) return;
        const container = containerRef.current;
        if (!container) return;
        const { w, h } = svgNativeSize;
        const cw = container.clientWidth || w;
        const ch = container.clientHeight || h;
        const svgUnitsPerPxX = (w / zoom) / cw;
        const svgUnitsPerPxY = (h / zoom) / ch;
        const dx = (e.clientX - dragRef.current.startX) * svgUnitsPerPxX;
        const dy = (e.clientY - dragRef.current.startY) * svgUnitsPerPxY;
        setPanX(dragRef.current.px - dx);
        setPanY(dragRef.current.py - dy);
    }, [svgNativeSize, zoom]);

    const onMouseUp = useCallback(() => { dragRef.current = null; }, []);

    // ── block click passthrough ───────────────────────────────────────────────
    const handleClick = (e) => {
        if (!onBlockSelect) return;
        const target = e.target.closest('[data-block-id]');
        if (target) {
            const blockId = target.getAttribute('data-block-id');
            if (blockId) { e.stopPropagation(); onBlockSelect(blockId); }
        }
    };

    // ── download helpers ──────────────────────────────────────────────────────
    const downloadBlob = (blob, filename) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    };

    const copySvgToClipboard = async () => {
        if (!svgMarkup) return;
        try {
            if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                await navigator.clipboard.writeText(svgMarkup);
            } else {
                const ta = document.createElement('textarea');
                ta.value = svgMarkup;
                ta.style.position = 'fixed';
                ta.style.left = '-9999px';
                document.body.appendChild(ta);
                ta.select();
                try { document.execCommand('copy'); } finally { ta.remove(); }
            }
            alert('SVG markup copied to clipboard');
        } catch (err) {
            alert('Copy failed: ' + (err?.message || err));
        }
    };

    const downloadSvg = () => {
        try {
            const svgBlob = new Blob([svgMarkup], { type: 'image/svg+xml;charset=utf-8' });
            downloadBlob(svgBlob, 'diagram.svg');
        } catch (err) {
            alert('SVG download failed: ' + (err?.message || err));
        }
    };

    // ── PNG export (SVG→canvas, high resolution) ──────────────────────────────
    const downloadPng = async () => {
        if (!processedMarkup) return;
        setBusy(true);
        try {
            const { blob } = await exportSvgToPng(processedMarkup, exportScale);
            downloadBlob(blob, 'diagram.png');
        } catch (err) {
            alert('PNG export failed: ' + (err?.message || err));
        } finally {
            setBusy(false);
        }
    };

    const copyPngToClipboard = async () => {
        if (!processedMarkup) return;
        setBusy(true);
        try {
            const { blob } = await exportSvgToPng(processedMarkup, exportScale);
            if (navigator.clipboard && navigator.clipboard.write && typeof window.ClipboardItem === 'function') {
                try {
                    const item = new window.ClipboardItem({ 'image/png': blob });
                    await navigator.clipboard.write([item]);
                    alert('PNG copied to clipboard');
                } catch (_) {
                    downloadBlob(blob, 'diagram.png');
                    alert('PNG copy not available; downloaded instead');
                }
            } else {
                downloadBlob(blob, 'diagram.png');
                alert('PNG copy not available in this browser; downloaded instead');
            }
        } catch (err) {
            alert('PNG copy failed: ' + (err?.message || err));
        } finally {
            setBusy(false);
        }
    };

    const recordGif = async ({ duration = 2000, fps = 8 } = {}) => {
        if (!containerRef.current) return;
        if (!window.GIF) { alert('GIF library not available'); return; }
        setBusy(true);
        try {
            const frameDelay = Math.round(1000 / fps);
            const frames = Math.max(2, Math.round((duration / 1000) * fps));
            const gif = new window.GIF({ workers: 2, quality: 10 });
            for (let i = 0; i < frames; i++) {
                // eslint-disable-next-line no-await-in-loop
                const canvas = await window.html2canvas(containerRef.current, { backgroundColor: null, scale: 1 });
                gif.addFrame(canvas, { copy: true, delay: frameDelay });
                // eslint-disable-next-line no-await-in-loop
                await new Promise((r) => setTimeout(r, frameDelay));
            }
            gif.on('finished', (blob) => { downloadBlob(blob, 'diagram.gif'); setBusy(false); });
            gif.render();
        } catch (err) {
            setBusy(false);
            alert('GIF export failed: ' + (err?.message || err));
        }
    };

    if (!svgMarkup) return null;

    const zoomPct = Math.round(zoom * 100);

    return (
        <div className={`${className}${maximized ? ' diagram-maximized' : ''}`}>

            {/* ── Zoom control bar ─────────────────────────────────────────── */}
            <div
                data-cy="zoom-controls"
                className="flex gap-1 mb-1 items-center flex-wrap"
            >
                <button
                    data-cy="zoom-in"
                    className={BTN}
                    onClick={zoomIn}
                    title="Zoom In"
                    aria-label="Zoom In"
                >+</button>
                <button
                    data-cy="zoom-out"
                    className={BTN}
                    onClick={zoomOut}
                    title="Zoom Out"
                    aria-label="Zoom Out"
                >−</button>
                <button
                    data-cy="zoom-reset"
                    className={BTN}
                    onClick={resetZoom}
                    title="Reset to 100%"
                    aria-label="Reset Zoom"
                >1:1</button>
                <button
                    data-cy="zoom-fit"
                    className={BTN}
                    onClick={fitToView}
                    title="Fit diagram to container"
                    aria-label="Fit to View"
                >Fit</button>
                <button
                    data-cy="zoom-maximize"
                    className={BTN}
                    onClick={() => setMaximized(m => !m)}
                    title={maximized ? 'Exit fullscreen' : 'Maximize diagram'}
                    aria-label={maximized ? 'Minimize' : 'Maximize'}
                >{maximized ? '⤡' : '⤢'}</button>
                <span
                    data-cy="zoom-level"
                    className="text-xs text-slate-400 ml-1 tabular-nums min-w-[3rem]"
                    aria-label="Current zoom level"
                >{zoomPct}%</span>
            </div>

            {/* ── Diagram canvas ───────────────────────────────────────────── */}
            <div
                ref={containerRef}
                data-cy={dataCy}
                onClick={handleClick}
                onMouseDown={onMouseDown}
                onMouseMove={onMouseMove}
                onMouseUp={onMouseUp}
                onMouseLeave={onMouseUp}
                className="diagram-export-container"
                style={{ cursor: 'grab', overflow: 'hidden' }}
                dangerouslySetInnerHTML={{ __html: processedMarkup }}
            />

            {/* ── Export controls ─────────────────────────────────────────── */}
            <div className="mt-2 flex gap-2 items-center flex-wrap">
                <button className={BTN} onClick={copySvgToClipboard} disabled={busy}>
                    Copy SVG
                </button>
                <button className={BTN} onClick={downloadSvg} disabled={busy}>
                    Download SVG
                </button>
                <select
                    data-cy="export-scale"
                    value={exportScale}
                    onChange={e => setExportScale(Number(e.target.value))}
                    className="text-xs px-1 py-1 rounded bg-slate-800/60 text-white border border-slate-600"
                    title="PNG export scale"
                    aria-label="PNG export scale"
                >
                    <option value={1}>1x</option>
                    <option value={2}>2x (HQ)</option>
                    <option value={3}>3x</option>
                    <option value={4}>4x</option>
                </select>
                <button
                    data-cy="download-png"
                    className={BTN}
                    onClick={downloadPng}
                    disabled={busy}
                    title={`Export PNG at ${exportScale}x`}
                >
                    Download PNG
                </button>
                <button className={BTN} onClick={copyPngToClipboard} disabled={busy}>
                    Copy PNG
                </button>
                <button
                    className={BTN_ACTIVE}
                    onClick={() => recordGif({ duration: 2000, fps: 8 })}
                    disabled={busy}
                >
                    {busy ? 'Processing…' : 'Record GIF'}
                </button>
            </div>
        </div>
    );
}
