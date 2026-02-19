import { useState } from 'react';
import DiagramViewer from '../diagram/DiagramViewer.jsx';

const STATIC_SVG = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" viewBox="0 0 800 300">
  <g id="group-postgres" class="node-group">
    <rect x="20" y="20" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
    <text x="120" y="55" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">Postgres</text>
  </g>
  <g id="group-vault" class="node-group">
    <rect x="260" y="20" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
    <text x="360" y="55" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">Vault</text>
  </g>
    <g id="group-minio" class="node-group">
        <rect x="500" y="20" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
        <text x="600" y="55" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">MinIO</text>
    </g>
    <g id="group-druid" class="node-group">
        <rect x="20" y="100" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
        <text x="120" y="135" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">Druid</text>
    </g>
    <g id="group-kafka" class="node-group">
        <rect x="260" y="100" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
        <text x="360" y="135" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">Kafka topics</text>
    </g>
    <g id="group-spark" class="node-group">
        <rect x="500" y="100" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
        <text x="600" y="135" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">Spark</text>
    </g>
    <g id="group-trino" class="node-group">
        <rect x="20" y="180" width="200" height="60" rx="6" fill="#eae8ff" stroke="#bdb8ff"/>
        <text x="120" y="215" text-anchor="middle" font-family="Arial" font-size="14" fill="#2b2b2b">Trino</text>
    </g>
  <!-- example connection -->
  <g id="edges"><line x1="220" y1="50" x2="260" y2="50" stroke="#999" stroke-width="2"/></g>
</svg>`;

export default function TestDiagramPage() {
    const [enableDebug, setEnableDebug] = useState(true);
    const [enableIcons, setEnableIcons] = useState(true);
    const [animated, setAnimated] = useState(false);

    // expose flags to window for Cypress and the DiagramViewer
    if (typeof window !== 'undefined') {
        window.DEBUG_SVG_RENDER = !!enableDebug;
        window.ENABLE_SVG_ICON_INJECTION = !!enableIcons;
        // default test icon requests for demo if enabled
        if (enableIcons) {
            window.__test_icon_requests = [
                { nodeText: 'Postgres', iconKey: 'postgres' },
                { nodeText: 'Vault', iconKey: 'vault' },
                { nodeText: 'MinIO', iconKey: 'minio' },
                { nodeText: 'Druid', iconKey: 'druid' },
                { nodeText: 'Kafka topics', iconKey: 'kafka' },
                { nodeText: 'Spark', iconKey: 'spark' },
                { nodeText: 'Trino', iconKey: 'trino' }
            ];
        } else {
            window.__test_icon_requests = [];
        }
        if (!enableIcons) window.__test_icon_requests = [];
    }

    const svgMarkup = animated ? STATIC_SVG.replace('<g id="group-postgres"', '<g id="group-postgres" class="animated"').replace('<g id="group-vault"', '<g id="group-vault" class="animated"') : STATIC_SVG;

    return (
        <div style={{ padding: 20, background: '#0b1220', minHeight: '100vh' }}>
            <div style={{ color: '#cbd5e1', marginBottom: 12 }}>
                <strong>Deterministic Diagram Test Page</strong>
            </div>
            <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                <label style={{ color: '#cbd5e1' }}><input type="checkbox" checked={enableDebug} onChange={(e) => setEnableDebug(e.target.checked)} /> DEBUG_SVG_RENDER</label>
                <label style={{ color: '#cbd5e1' }}><input type="checkbox" checked={enableIcons} onChange={(e) => setEnableIcons(e.target.checked)} /> ENABLE_SVG_ICON_INJECTION</label>
                <label style={{ color: '#cbd5e1' }}><input type="checkbox" checked={animated} onChange={(e) => setAnimated(e.target.checked)} /> animated</label>
            </div>

            <div style={{ background: '#071024', padding: 16, borderRadius: 8 }}>
                <DiagramViewer svgMarkup={svgMarkup} className="test-inline-diagram" dataCy="inline-diagram" />
            </div>
        </div>
    );
}
