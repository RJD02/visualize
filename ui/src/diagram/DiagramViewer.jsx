
import { useRef, useState } from 'react';
import { useEffect, useMemo } from 'react';
import { postProcessSvgWithIcons } from './iconRegistry.js';

export default function DiagramViewer({ svgMarkup, className = '', onBlockSelect, dataCy }) {
    const containerRef = useRef(null);
    const [busy, setBusy] = useState(false);
    // processed markup may include injected icons when enabled
    const processedMarkup = useMemo(() => {
        try {
            if (typeof window !== 'undefined' && window.ENABLE_SVG_ICON_INJECTION && svgMarkup && svgMarkup.includes('<svg')) {
                return postProcessSvgWithIcons(svgMarkup);
            }
        } catch (e) {
            // swallow
        }
        return svgMarkup;
    }, [svgMarkup]);

    if (!svgMarkup) return null;

    const handleClick = (e) => {
        if (!onBlockSelect) return;
        const target = e.target.closest('[data-block-id]');
        if (target) {
            const blockId = target.getAttribute('data-block-id');
            if (blockId) {
                e.stopPropagation();
                onBlockSelect(blockId);
            }
        }
    };

    // Debug: detect render mode and optionally attach data-testid
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
                    // expose for Cypress
                    window.__diagramRenderDebug = { rendering_mode: mode, childTag: child && child.tagName, hasSvgDesc };
                    root.setAttribute('data-testid', 'diagram-root');
                } catch (e) {
                    // ignore
                }
            }
        } catch (e) {
            // ignore
        }
    }, [processedMarkup]);

    const copySvgToClipboard = async () => {
        if (!svgMarkup) return;
        try {
            if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
                await navigator.clipboard.writeText(svgMarkup);
            } else {
                // fallback for environments without Clipboard API (e.g., some Electron or insecure origins)
                const ta = document.createElement('textarea');
                ta.value = svgMarkup;
                // prevent scrolling to bottom
                ta.style.position = 'fixed';
                ta.style.left = '-9999px';
                document.body.appendChild(ta);
                ta.select();
                try {
                    document.execCommand('copy');
                } finally {
                    ta.remove();
                }
            }
            // quick visual feedback
            alert('SVG markup copied to clipboard');
        } catch (err) {
            alert('Copy failed: ' + (err?.message || err));
        }
    };

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

    const downloadSvg = () => {
        try {
            const svgBlob = new Blob([svgMarkup], { type: 'image/svg+xml;charset=utf-8' });
            downloadBlob(svgBlob, 'diagram.svg');
        } catch (err) {
            alert('SVG download failed: ' + (err?.message || err));
        }
    };

    const downloadPng = async () => {
        if (!containerRef.current) return;
        setBusy(true);
        try {
            // Ensure html2canvas is available
            const h2c = window.html2canvas || window.html2canvas;
            if (!h2c || typeof h2c !== 'function') {
                setBusy(false);
                alert('PNG export requires html2canvas library (not available in this environment).');
                return;
            }
            // Render the live element to a canvas using html2canvas (preserves current animation frame)
            const canvas = await h2c(containerRef.current, { backgroundColor: null, scale: window.devicePixelRatio || 1 });
            if (!canvas) {
                setBusy(false);
                alert('PNG export failed: rendering returned no canvas');
                return;
            }
            canvas.toBlob((blob) => {
                if (blob) downloadBlob(blob, 'diagram.png');
                else alert('PNG export failed');
                setBusy(false);
            }, 'image/png');
        } catch (err) {
            setBusy(false);
            alert('PNG export failed: ' + (err?.message || err));
        }
    };

    const copyPngToClipboard = async () => {
        if (!containerRef.current) return;
        setBusy(true);
        try {
            const h2c = window.html2canvas || window.html2canvas;
            if (!h2c || typeof h2c !== 'function') {
                setBusy(false);
                alert('PNG copy requires html2canvas library (not available).');
                return;
            }
            const canvas = await h2c(containerRef.current, { backgroundColor: null, scale: window.devicePixelRatio || 1 });
            if (!canvas) {
                setBusy(false);
                alert('PNG copy failed: rendering returned no canvas');
                return;
            }
            canvas.toBlob(async (blob) => {
                if (!blob) {
                    alert('PNG copy failed');
                    setBusy(false);
                    return;
                }
                // Use Clipboard API if available
                if (navigator.clipboard && navigator.clipboard.write && typeof window.ClipboardItem === 'function') {
                    try {
                        const item = new window.ClipboardItem({ 'image/png': blob });
                        await navigator.clipboard.write([item]);
                        alert('PNG copied to clipboard');
                    } catch (err) {
                        // fallback to download
                        downloadBlob(blob, 'diagram.png');
                        alert('PNG copy not available; downloaded instead');
                    }
                } else {
                    // fallback: download
                    downloadBlob(blob, 'diagram.png');
                    alert('PNG copy not available in this browser; downloaded instead');
                }
                setBusy(false);
            }, 'image/png');
        } catch (err) {
            setBusy(false);
            alert('PNG copy failed: ' + (err?.message || err));
        }
    };

    const recordGif = async ({ duration = 2000, fps = 8 } = {}) => {
        if (!containerRef.current) return;
        if (!window.GIF) {
            alert('GIF library not available');
            return;
        }
        setBusy(true);
        try {
            const frameDelay = Math.round(1000 / fps);
            const frames = Math.max(2, Math.round((duration / 1000) * fps));
            // Do not hard-code an external CDN worker script — if `gif.js` is provided, it should
            // resolve its worker script relative to the installation. If you want to enable GIF
            // export in production, either vendor `gif.js` locally or install it as a dependency.
            const gif = new window.GIF({ workers: 2, quality: 10 });

            for (let i = 0; i < frames; i++) {
                // capture the live DOM (this captures current animation frame)
                // using html2canvas which returns a canvas
                // wait a tick between captures to allow animations to progress
                // capture
                // eslint-disable-next-line no-await-in-loop
                const canvas = await window.html2canvas(containerRef.current, { backgroundColor: null, scale: 1 });
                gif.addFrame(canvas, { copy: true, delay: frameDelay });
                // wait to next frame
                // eslint-disable-next-line no-await-in-loop
                await new Promise((r) => setTimeout(r, frameDelay));
            }

            gif.on('finished', function (blob) {
                downloadBlob(blob, 'diagram.gif');
                setBusy(false);
            });
            gif.render();
        } catch (err) {
            setBusy(false);
            alert('GIF export failed: ' + (err?.message || err));
        }
    };

    return (
        <div className={className}>
            <div
                ref={containerRef}
                data-cy={dataCy}
                onClick={handleClick}
                className="diagram-export-container"
                dangerouslySetInnerHTML={{ __html: processedMarkup }}
            />
            <div className="mt-2 flex gap-2">
                <button className="text-xs px-2 py-1 rounded bg-slate-800/60 hover:bg-slate-800/80" onClick={copySvgToClipboard} disabled={busy}>
                    Copy SVG
                </button>
                <button className="text-xs px-2 py-1 rounded bg-slate-800/60 hover:bg-slate-800/80" onClick={downloadSvg} disabled={busy}>
                    Download SVG
                </button>
                <button className="text-xs px-2 py-1 rounded bg-slate-800/60 hover:bg-slate-800/80" onClick={downloadPng} disabled={busy}>
                    Download PNG
                </button>
                <button className="text-xs px-2 py-1 rounded bg-slate-800/60 hover:bg-slate-800/80" onClick={copyPngToClipboard} disabled={busy}>
                    Copy PNG
                </button>
                <button className="text-xs px-2 py-1 rounded bg-indigo-700 hover:bg-indigo-600 text-white" onClick={() => recordGif({ duration: 2000, fps: 8 })} disabled={busy}>
                    {busy ? 'Processing…' : 'Record GIF'}
                </button>
            </div>
        </div>
    );
}
