// Deterministic icon registry and SVG post-processor for injecting allowed icons into inline SVGs.
// Contains local icon symbols, deterministic resolver, and post-processing helpers.

const ICONS = {
    // generic
    'generic-database': { viewBox: '0 0 24 24', path: 'M12 2C7.58 2 4 3.79 4 6v12c0 2.21 3.58 4 8 4s8-1.79 8-4V6c0-2.21-3.58-4-8-4z' },
    'generic-service': { viewBox: '0 0 24 24', path: 'M12 2a5 5 0 015 5v10a5 5 0 01-10 0V7a5 5 0 015-5z' },

    // infra / brand-like icons (kept simple and local — do NOT fetch at runtime)
    postgres: { viewBox: '0 0 24 24', path: 'M12 2C8 2 3 4 3 8v8c0 4 5 6 9 6s9-2 9-6V8c0-4-5-6-9-6z' },
    minio: { viewBox: '0 0 24 24', path: 'M3 7h18v10H3z' },
    kafka: { viewBox: '0 0 24 24', path: 'M4 12a8 8 0 1116 0 8 8 0 01-16 0zm2 0h12' },
    spark: { viewBox: '0 0 24 24', path: 'M12 2l2.5 6L21 10l-5 4 1.5 6L12 16l-5.5 4L8 14 3 10l6.5-2L12 2z' },
    trino: { viewBox: '0 0 24 24', path: 'M12 2l9 21H3L12 2z' },
    druid: { viewBox: '0 0 24 24', path: 'M12 2l3 7h7l-5.5 4 2 7L12 16 5.5 20l2-7L2 9h7z' },
    vault: { viewBox: '0 0 24 24', path: 'M12 1L3 5v6c0 5 3.58 9.74 9 11 5.42-1.26 9-6 9-11V5l-9-4z' },
    kubernetes: { viewBox: '0 0 24 24', path: 'M12 2l4 2v4l4 2-4 2v4l-4 2-4-2v-4L4 10l4-2V4l4-2z' },
    airflow: { viewBox: '0 0 24 24', path: 'M2 12c0-5 4-9 9-9s9 4 9 9-4 9-9 9S2 17 2 12z' },
    superset: { viewBox: '0 0 24 24', path: 'M3 3h18v2H3V3zm0 4h10v2H3V7zm0 4h18v2H3v-2z' }
};

// Helper: deterministic icon resolver
function normalizeLabel(label) {
    return (label || '').toString().trim().toLowerCase().replace(/[._"'`,:()\[\]{}]/g, '');
}

const KEYWORDS = {
    postgres:      ['postgres', 'postgresql', 'metadata db', 'metadatadb'],
    kafka:         ['kafka'],
    minio:         ['minio', 'object store', 'objectstore', 'ceph', 's3'],
    spark:         ['spark'],
    trino:         ['trino', 'presto'],
    vault:         ['vault', 'secrets'],
    kubernetes:    ['kubernetes', 'k8s'],
    airflow:       ['airflow'],
    superset:      ['superset'],
    redis:         ['redis', 'cache'],
    mongodb:       ['mongodb', 'mongo'],
    druid:         ['druid'],
};

export function resolveIconForNode(label, stereotype) {
    const n = normalizeLabel(label);
    for (const key of Object.keys(KEYWORDS)) {
        for (const kw of KEYWORDS[key]) {
            if (n.includes(kw)) return key;
        }
    }
    // fallback by stereotype
    if (stereotype) {
        const s = normalizeLabel(stereotype);
        if (s.includes('db') || s.includes('database')) return 'generic-database';
        if (s.includes('service') || s.includes('app')) return 'generic-service';
        if (s.includes('external')) return 'generic-database';
    }
    return null;
}

// Auto-assign icons by scanning text/foreignObject nodes inside provided SVG element.
// Handles both internal renderer (<text>) and Mermaid (<foreignObject> with HTML).
function autoAssignIconsFromSvg(svg) {
    const requests = [];
    const seen = new Set();
    // SVG <text> elements (internal renderer)
    const texts = Array.from(svg.querySelectorAll('text'));
    // Mermaid foreignObject HTML children — querySelectorAll works across namespaces
    const foTexts = Array.from(svg.querySelectorAll('foreignObject p, foreignObject span, foreignObject div'));
    for (const t of [...texts, ...foTexts]) {
        const text = (t.textContent || '').trim();
        if (!text || seen.has(text)) continue;
        seen.add(text);
        const icon = resolveIconForNode(text, null);
        if (icon) requests.push({ nodeText: text, iconKey: icon });
    }
    return requests;
}

export function postProcessSvgWithIcons(svgString) {
    if (!svgString) return svgString;
    try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(svgString, 'image/svg+xml');
        const svg = doc.querySelector('svg');
        if (!svg) return svgString;

        // Ensure <defs>
        let defs = svg.querySelector('defs');
        if (!defs) {
            defs = doc.createElementNS('http://www.w3.org/2000/svg', 'defs');
            svg.insertBefore(defs, svg.firstChild);
        }

        // Inject symbols for each allowed icon (id prefixed)
        Object.keys(ICONS).forEach((key) => {
            const existing = defs.querySelector('#fa_icon_' + key);
            if (existing) return;
            const symbol = doc.createElementNS('http://www.w3.org/2000/svg', 'symbol');
            symbol.setAttribute('id', 'fa_icon_' + key);
            symbol.setAttribute('viewBox', ICONS[key].viewBox);
            const path = doc.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', ICONS[key].path);
            symbol.appendChild(path);
            defs.appendChild(symbol);
        });

        // If tests request icon injection, use window.__test_icon_requests array
        let requests = (typeof window !== 'undefined' && window.__test_icon_requests) || [];

        // If no explicit requests provided, perform deterministic auto-assignment based on node labels
        if ((!requests || requests.length === 0) && typeof window !== 'undefined' && window.ENABLE_SVG_ICON_INJECTION) {
            requests = autoAssignIconsFromSvg(svg);
            if (window.DEBUG_SVG_RENDER) console.debug('autoAssignIconsFromSvg', requests);
        }
        if (!requests || requests.length === 0) {
            if (window.DEBUG_SVG_RENDER) console.debug('postProcessSvgWithIcons: no icon requests');
            return new XMLSerializer().serializeToString(doc);
        }

        // Icon style — use explicit dark-blue fill for contrast on light node backgrounds.
        // Brand SVGs injected server-side carry their own colours; this style covers the
        // client-side simple-path fallback icons.
        let styleEl = svg.querySelector('style#fa_node_icon_style');
        if (!styleEl) {
            styleEl = doc.createElementNS('http://www.w3.org/2000/svg', 'style');
            styleEl.setAttribute('id', 'fa_node_icon_style');
            styleEl.textContent = '.node-icon { fill: #1e40af; opacity: 0.88; transition: opacity 200ms; pointer-events: none; } .node-icon.hidden{opacity:0}';
            svg.insertBefore(styleEl, svg.firstChild);
        }

        // Ensure svg root has xlink namespace for older renderers when using xlink:href
        if (!svg.getAttribute('xmlns:xlink')) svg.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');

        // For each request, find the node group that contains the matching label text.
        // Supports both <text> elements (internal renderer) and <foreignObject> HTML
        // children like <p>/<span> (Mermaid renderer).
        let inserted = 0;
        requests.forEach((req) => {
            const nodeText = (req.nodeText || '').trim();
            const iconKey = req.iconKey;
            if (!nodeText || !ICONS[iconKey]) return;

            // Search SVG text elements + Mermaid foreignObject HTML children
            const candidates = [
                ...Array.from(svg.querySelectorAll('text')),
                ...Array.from(svg.querySelectorAll('foreignObject p, foreignObject span, foreignObject div')),
            ];
            let targetGroup = null;
            for (const t of candidates) {
                if (!t.textContent || t.textContent.trim().toLowerCase() !== nodeText.toLowerCase()) continue;
                // Walk up to the nearest <g> ancestor.  For Mermaid nodes the innermost
                // <g class="label"> does not have a <rect>; keep walking until we find one
                // that does, or until we reach a <g class="node ..."> (outermost node group).
                let g = t.parentNode;
                while (g && g.nodeName.toLowerCase() !== 'svg') {
                    if (g.nodeName.toLowerCase() === 'g') {
                        const cls = g.getAttribute('class') || '';
                        // Stop at the outermost node group or when we have a rect sibling
                        if (cls.split(' ').includes('node') || g.querySelector(':scope > rect')) break;
                    }
                    g = g.parentNode;
                }
                if (g && g.nodeName.toLowerCase() === 'g') { targetGroup = g; break; }
            }
            if (!targetGroup) return;

            // Skip groups where server-side brand icon was already injected
            // (data-icon-injected="1" is set by src/diagram/icon_injector.py).
            // This prevents client-side circle-path placeholders from overriding
            // the real brand SVG symbols injected server-side (BUG-ICON-CIRCLE-RENDER-01).
            if (targetGroup.getAttribute('data-icon-injected') === '1') return;

            // Create a <use> referencing the symbol
            const use = doc.createElementNS('http://www.w3.org/2000/svg', 'use');
            use.setAttribute('href', '#fa_icon_' + iconKey);
            use.setAttributeNS('http://www.w3.org/1999/xlink', 'xlink:href', '#fa_icon_' + iconKey);
            use.setAttribute('class', 'node-icon');

            // Position relative to the background <rect> (works for both internal-renderer
            // and Mermaid nodes where the rect is centred at group origin with negative x/y).
            const rect = targetGroup.querySelector('rect');
            const textEl = targetGroup.querySelector('text');
            const ICON_SIZE = 20;
            let tx = 0, ty = 0;
            if (rect) {
                const rx = parseFloat(rect.getAttribute('x') || '0');
                const ry = parseFloat(rect.getAttribute('y') || '0');
                const rh = parseFloat(rect.getAttribute('height') || String(ICON_SIZE));
                tx = rx + 4;
                ty = ry + (rh - ICON_SIZE) / 2;
            } else if (textEl) {
                const txAttr = parseFloat(textEl.getAttribute('x') || '0');
                const tyAttr = parseFloat(textEl.getAttribute('y') || '0');
                tx = txAttr - ICON_SIZE - 4;
                ty = tyAttr - ICON_SIZE / 2;
            }

            use.setAttribute('x', String(tx));
            use.setAttribute('y', String(ty));
            use.setAttribute('width', String(ICON_SIZE));
            use.setAttribute('height', String(ICON_SIZE));
            targetGroup.insertBefore(use, targetGroup.firstChild);
            inserted += 1;
        });

        if (window.DEBUG_SVG_RENDER) {
            console.debug('postProcessSvgWithIcons: injected symbols count=', Object.keys(ICONS).length);
            console.debug('postProcessSvgWithIcons: inserted <use> elements=', inserted);
        }

        return new XMLSerializer().serializeToString(doc);
    } catch (e) {
        return svgString;
    }
}

export default ICONS;

