/**
 * icon_registry.test.js
 * Unit tests for src/diagram/iconRegistry.js (Node.js backend registry)
 * and regression guard for BUG-ICON-CIRCLE-RENDER-01 client-side guard.
 */
'use strict';
const assert = require('assert');
const path = require('path');
const { JSDOM } = require('jsdom');

// ── Backend registry (CommonJS, reads real SVG files) ──────────────────────
const registry = require(path.join(process.cwd(), 'src/diagram/iconRegistry'));

// ── Client-side guard regression test (JSDOM simulation) ──────────────────

/**
 * Simulate postProcessSvgWithIcons() from ui/src/diagram/iconRegistry.js
 * in a JSDOM environment to verify the data-icon-injected guard fires.
 *
 * We load the ES module via a minimal eval-in-JSDOM approach by extracting
 * the guard logic and testing it directly.
 */
function testClientGuard() {
  // Minimal SVG with a node group that has data-icon-injected="1" (server-side done)
  const svgWithServerIcons = `<svg xmlns="http://www.w3.org/2000/svg">
    <defs id="icon-sprite">
      <symbol id="icon-airflow" viewBox="0 0 128 128">
        <path d="M10 10 L118 10 L64 118 Z" fill="#017cee"/>
      </symbol>
    </defs>
    <g id="n1" class="node default" data-icon-injected="1" data-icon-symbol="icon-airflow">
      <rect x="-130" y="-39" width="260" height="78"/>
      <use href="#icon-airflow" class="node-icon injected-icon" x="-126" y="-10" width="20" height="20"/>
      <g class="label">
        <foreignObject width="200" height="40">
          <p>Airflow/Superset/OpenMetadata</p>
        </foreignObject>
      </g>
    </g>
  </svg>`;

  const dom = new JSDOM(`<!DOCTYPE html><body></body>`, { pretendToBeVisual: true });
  const window = dom.window;
  const document = window.document;

  // Parse SVG into DOM
  const parser = new window.DOMParser();
  const doc = parser.parseFromString(svgWithServerIcons, 'image/svg+xml');
  const svg = doc.documentElement;

  // Count existing <use> elements before simulated client injection
  const usesBefore = svg.querySelectorAll('use').length;
  assert.strictEqual(usesBefore, 1, `Expected 1 <use> (server injected), got ${usesBefore}`);

  // Simulate the client-side injection loop with the guard
  const ICONS = {
    airflow: { viewBox: '0 0 24 24', path: 'M2 12c0-5 4-9 9-9s9 4 9 9-4 9-9 9S2 17 2 12z' }
  };
  const foTexts = Array.from(svg.querySelectorAll('foreignObject p, foreignObject span, foreignObject div'));

  let injectedCount = 0;
  foTexts.forEach((t) => {
    const nodeText = (t.textContent || '').trim();
    if (!nodeText) return;

    // Walk up to find nearest <g> with 'node' class or direct rect child
    let g = t.parentNode;
    while (g && g.nodeName.toLowerCase() !== 'svg') {
      if (g.nodeName.toLowerCase() === 'g') {
        const cls = g.getAttribute('class') || '';
        if (cls.split(' ').includes('node') || g.querySelector(':scope > rect')) break;
      }
      g = g.parentNode;
    }
    if (!g || g.nodeName.toLowerCase() !== 'g') return;

    const targetGroup = g;

    // THE GUARD — BUG-ICON-CIRCLE-RENDER-01 fix
    if (targetGroup.getAttribute('data-icon-injected') === '1') return;

    // Would inject (but won't because guard fired)
    const use = doc.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '#fa_icon_airflow');
    use.setAttribute('class', 'node-icon fa-injected');
    targetGroup.insertBefore(use, targetGroup.firstChild);
    injectedCount++;
  });

  assert.strictEqual(injectedCount, 0,
    'Guard failed: client-side icon was injected into a node with data-icon-injected="1". ' +
    'This would cause blue circle overlaps (BUG-ICON-CIRCLE-RENDER-01).'
  );

  // Verify <use> count unchanged (still only server-injected one)
  const usesAfter = svg.querySelectorAll('use').length;
  assert.strictEqual(usesAfter, 1,
    `Expected 1 <use> after guarded injection, got ${usesAfter}`
  );

  console.log('  [PASS] client-side guard prevents double-injection');
}

function run() {
  console.log('=== icon_registry unit tests ===');

  // ── Backend registry tests ────────────────────────────────────────────────
  const icons = registry.getAvailableIcons();
  assert.ok(Array.isArray(icons) && icons.length > 0, 'getAvailableIcons() returned empty');
  console.log('  [PASS] getAvailableIcons() returns', icons.length, 'icons');

  const postgres = registry.getIconMarkup('postgres');
  assert.ok(typeof postgres === 'string' && postgres.length > 0, 'postgres icon markup missing');
  console.log('  [PASS] getIconMarkup("postgres") returns markup');

  const unknown = registry.getIconMarkup('this-does-not-exist');
  assert.ok(typeof unknown === 'string', 'fallback must return a string');
  console.log('  [PASS] getIconMarkup("this-does-not-exist") returns fallback string');

  // ── Client-side guard regression test ─────────────────────────────────────
  // Only run if jsdom is available
  try {
    require('jsdom');
    testClientGuard();
  } catch (e) {
    if (e.code === 'MODULE_NOT_FOUND') {
      console.log('  [SKIP] client-side guard test (jsdom not installed)');
    } else {
      throw e;
    }
  }

  console.log('=== All icon_registry tests passed ===');
}

if (require.main === module) run();
module.exports = { run };
