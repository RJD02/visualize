import React, { useEffect, useRef } from 'react';
import './test.css';

// Deterministic test page for SVG icon embedding verification.
// Exposes window helpers used by Cypress tests.

function InlineMinimal() {
    // Minimal inline SVG with a placeholder where test will inject symbol/use
    return (
        <div data-cy="phase-minimal">
            <svg id="minimal-svg" width="200" height="80" xmlns="http://www.w3.org/2000/svg">
                <rect x="0" y="0" width="200" height="80" fill="#f6f6f6" stroke="#ddd" />
                <g id="label-group">
                    <text x="110" y="40" fontSize="14">Test Node</text>
                </g>
            </svg>
        </div>
    );
}

function RealNodeSim() {
    return (
        <div data-cy="phase-real">
            <svg id="real-svg" width="400" height="160" xmlns="http://www.w3.org/2000/svg">
                <rect x="0" y="0" width="400" height="160" fill="#fff" stroke="#eee" />
                <g id="node-postgres" transform="translate(20,20)">
                    <rect x="0" y="0" width="120" height="60" rx="6" ry="6" fill="#ffffff" stroke="#9aa" />
                    <text x="12" y="34" fontSize="14">Postgres</text>
                </g>
            </svg>
        </div>
    );
}

function AnimationSim() {
    return (
        <div data-cy="phase-anim">
            <svg id="anim-svg" width="300" height="120" xmlns="http://www.w3.org/2000/svg">
                <rect x="0" y="0" width="300" height="120" fill="#fff" stroke="#eee" />
                <g id="anim-node" className="anim-node" transform="translate(30,30)">
                    <rect x="0" y="0" width="100" height="60" rx="6" ry="6" fill="#fff" stroke="#9aa" />
                    <text x="12" y="34" fontSize="14">Animated</text>
                </g>
            </svg>
        </div>
    );
}

export default function IconInjectionTestPage() {
    const mountedRef = useRef(false);

    useEffect(() => {
        if (mountedRef.current) return;
        mountedRef.current = true;

        // Enable debug flag for scripts/tests
        window.DEBUG_SVG_RENDER = true;

        // Helper: check render mode for a container element
        window.__detectRenderMode = function (selector) {
            const el = document.querySelector(selector);
            if (!el) return { found: false };
            const first = el.firstElementChild;
            return {
                found: true,
                rootTag: el.tagName,
                firstChildTag: first ? first.tagName : null,
                hasInlineSvg: !!el.querySelector('svg'),
                hasImg: !!el.querySelector('img')
            };
        };

        // Helper: inject a symbol and use into a given SVG by id
        window.__injectSymbolAndUse = function (svgId, symbolId, viewBox, symbolSvgString, targetSelector) {
            const svg = document.getElementById(svgId);
            if (!svg) return { ok: false, reason: 'no-svg' };
            // ensure defs
            let defs = svg.querySelector('defs');
            if (!defs) {
                defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
                svg.insertBefore(defs, svg.firstChild);
            }
            // create symbol container
            const parser = new DOMParser();
            const symDoc = parser.parseFromString(`<svg xmlns='http://www.w3.org/2000/svg'>${symbolSvgString}</svg>`, 'image/svg+xml');
            const inner = Array.from(symDoc.documentElement.children);
            const symbol = document.createElementNS('http://www.w3.org/2000/svg', 'symbol');
            symbol.setAttribute('id', symbolId);
            if (viewBox) symbol.setAttribute('viewBox', viewBox);
            inner.forEach(node => symbol.appendChild(document.importNode(node, true)));
            defs.appendChild(symbol);

            // append use into target element
            const target = targetSelector ? svg.querySelector(targetSelector) : svg;
            if (!target) return { ok: false, reason: 'no-target' };
            const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
            // set both modern and legacy href attributes
            use.setAttribute('href', `#${symbolId}`);
            use.setAttribute('xlink:href', `#${symbolId}`);
            use.setAttribute('x', '4');
            use.setAttribute('y', '4');
            use.setAttribute('width', '20');
            use.setAttribute('height', '20');
            target.appendChild(use);
            return { ok: true };
        };

        // Helper: compute visibility metrics
        window.__getVisibilityForSelector = function (sel) {
            const el = document.querySelector(sel);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            const cs = window.getComputedStyle(el);
            return {
                width: r.width,
                height: r.height,
                display: cs.display,
                opacity: cs.opacity
            };
        };

    }, []);

    return (
        <div style={{ padding: 20 }}>
            <h3>Icon Injection Deterministic Test Page</h3>
            <p>This page provides deterministic inline SVGs for phased testing.</p>
            <InlineMinimal />
            <RealNodeSim />
            <AnimationSim />
        </div>
    );
}
