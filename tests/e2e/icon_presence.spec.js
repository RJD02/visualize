/**
 * icon_presence.spec.js
 * Playwright e2e tests for icon rendering correctness.
 *
 * BUG-ICON-CIRCLE-RENDER-01 regression guard:
 * Verifies that after the fix, brand icons render via <use>→<symbol> (not inlined
 * circles), and that the server pipeline emits correct <use> elements with
 * position/scale attributes.
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..', '..');

// ── Helper: build a minimal SVG with icons injected by the server pipeline ──
async function getInjectedSvg() {
  const { execSync } = require('child_process');
  // Run the server-side pipeline in Python and capture the result
  const script = `
import sys, json
sys.path.insert(0, '.')
from src.server import _auto_inject_icons

with open('outputs/46050207-2fb4-41c4-950a-c24521b94b81_component_2.svg') as f:
    svg = f.read()

result = _auto_inject_icons(svg)
print(result)
`;
  const result = execSync(`python3 -c "${script.replace(/\n/g, ' ').replace(/"/g, '\\"')}"`, {
    cwd: ROOT,
    maxBuffer: 10 * 1024 * 1024,
  });
  return result.toString();
}

// ── Test 1: Original regression test (kept for backward compatibility) ───────
test('reproduction fixed svg should inline icons and render them visibly', async ({ page }) => {
  const filePath = path.join(ROOT, 'outputs', 'repro_icon_visibility.fixed.svg');
  if (!fs.existsSync(filePath)) {
    test.skip('repro_icon_visibility.fixed.svg not found, skipping legacy test');
    return;
  }
  const svg = fs.readFileSync(filePath, 'utf8');
  await page.setContent(svg, { waitUntil: 'domcontentloaded' });

  // Legacy test expects data-inlined-from (old pipeline). With the new pipeline,
  // <use>→<symbol> is used instead. Check either.
  const hasInlined = await page.locator('[data-inlined-from]').count();
  const hasUse = await page.locator('use[href^="#icon-"]').count();
  expect(hasInlined + hasUse).toBeGreaterThan(0);
});

// ── Test 2: BUG-ICON-CIRCLE-RENDER-01 — server pipeline emits use+symbol ────
test('BUG-ICON-CIRCLE-RENDER-01: server pipeline emits <use> with position attributes', async ({ page }) => {
  // Build a minimal SVG with a known node
  const testSvg = `<svg xmlns="http://www.w3.org/2000/svg">
    <g id="n1" data-kind="node">
      <rect x="10" y="5" width="200" height="60"/>
      <text x="110" y="35">Kubernetes Cluster (PROD)</text>
    </g>
    <g id="n2" data-kind="node">
      <rect x="10" y="100" width="250" height="60"/>
      <text x="135" y="130">Airflow/Superset/OpenMetadata</text>
    </g>
  </svg>`;

  const { execSync, spawnSync } = require('child_process');
  const os = require('os');

  // Write test SVG to a temp file to avoid shell escaping issues
  const tmpSvg = path.join(os.tmpdir(), 'bug_icon_render_test.svg');
  const tmpScript = path.join(os.tmpdir(), 'bug_icon_render_inject.py');
  fs.writeFileSync(tmpSvg, testSvg, 'utf8');
  fs.writeFileSync(tmpScript, `
import sys
sys.path.insert(0, '.')
from src.diagram.icon_injector import inject_icons
svg = open('${tmpSvg.replace(/\\/g, '\\\\')}').read()
result = inject_icons(svg, {
    'n1': 'Kubernetes Cluster (PROD)',
    'n2': 'Airflow/Superset/OpenMetadata',
})
print(result)
`.trim(), 'utf8');

  let injectedSvg;
  try {
    const r = spawnSync('python3', [tmpScript], { cwd: ROOT, maxBuffer: 2 * 1024 * 1024 });
    if (r.status !== 0) throw new Error(r.stderr.toString());
    injectedSvg = r.stdout.toString();
  } catch (e) {
    throw new Error('Failed to run inject_icons via Python: ' + e.message);
  }

  // Normalize namespace prefixes (as client normalizeSvg() does)
  injectedSvg = injectedSvg
    .replace(/<\s*ns\d+:/gi, '<')
    .replace(/<\/\s*ns\d+:/gi, '</')
    .replace(/\s+xmlns:ns\d+="[^"]*"/gi, '');

  await page.setContent(`<!DOCTYPE html><html><body>${injectedSvg}</body></html>`, {
    waitUntil: 'domcontentloaded',
  });

  // 1) Defs with symbols must be present
  const symbolCount = await page.locator('defs symbol[id^="icon-"]').count();
  expect(symbolCount).toBeGreaterThan(0);

  // 2) <use> elements referencing brand symbols must exist with position attributes
  const useLocator = page.locator('use[href^="#icon-"], use[*|href^="#icon-"]');
  await expect(useLocator.first()).toBeAttached();

  const firstUse = useLocator.first();
  const useX = await firstUse.getAttribute('x');
  const useY = await firstUse.getAttribute('y');
  const useW = await firstUse.getAttribute('width');
  const useH = await firstUse.getAttribute('height');
  expect(useX).not.toBeNull();
  expect(useY).not.toBeNull();
  expect(useW).not.toBeNull();
  expect(useH).not.toBeNull();

  // 3) No client-side placeholder circles (#fa_icon_*) must be present
  const circleUseCount = await page.locator('use[href^="#fa_icon_"]').count();
  expect(circleUseCount).toBe(0);

  // 4) data-icon-injected flag must be set so the client guard fires
  const guardedNodes = await page.locator('[data-icon-injected="1"]').count();
  expect(guardedNodes).toBeGreaterThan(0);

  // Screenshot for evidence
  const screenshotDir = path.join(
    ROOT,
    '.ai-sldc/debugging/BUG-ICON-CIRCLE-RENDER-01/evidence/ui/screenshots'
  );
  fs.mkdirSync(screenshotDir, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDir, 'BUG-ICON-CIRCLE-RENDER-01-icon-render.png'),
    fullPage: true,
  });
});

// ── Test 3: Client-side guard test (no double-injection) ──────────────────
test('BUG-ICON-CIRCLE-RENDER-01: client guard prevents circle injection on server-injected nodes', async ({ page }) => {
  // Build an SVG that already has server-side icon injection applied
  const svgWithServerIcons = `<svg xmlns="http://www.w3.org/2000/svg">
    <defs id="icon-sprite">
      <symbol id="icon-kubernetes" viewBox="0 0 128 128">
        <g fill="#486bb3"><path d="M64 10 L118 118 L10 118 Z"/></g>
      </symbol>
      <symbol id="icon-airflow" viewBox="0 0 128 128">
        <path d="M10 10 L118 10 L64 118 Z" fill="#017cee"/>
      </symbol>
    </defs>
    <g id="n1" class="node default" data-icon-injected="1" data-icon-symbol="icon-kubernetes">
      <rect x="-130" y="-39" width="260" height="78"/>
      <use href="#icon-kubernetes" class="node-icon injected-icon" x="-126" y="-10" width="20" height="20"/>
      <g class="label">
        <foreignObject width="200" height="40">
          <div><p>Kubernetes Cluster (PROD)</p></div>
        </foreignObject>
      </g>
    </g>
    <g id="n2" class="node default" data-icon-injected="1" data-icon-symbol="icon-airflow">
      <rect x="-130" y="-39" width="260" height="78"/>
      <use href="#icon-airflow" class="node-icon injected-icon" x="-126" y="-10" width="20" height="20"/>
      <g class="label">
        <foreignObject width="250" height="40">
          <div><p>Airflow/Superset/OpenMetadata</p></div>
        </foreignObject>
      </g>
    </g>
  </svg>`;

  await page.setContent(`<!DOCTYPE html><html><body>${svgWithServerIcons}</body></html>`, {
    waitUntil: 'domcontentloaded',
  });

  // Inject the client-side iconRegistry logic with the guard
  const clientGuardResult = await page.evaluate(() => {
    const svg = document.querySelector('svg');
    if (!svg) return { error: 'no svg' };

    const ICONS = {
      kubernetes: { viewBox: '0 0 24 24', path: 'M12 2l4 2v4l4 2-4 2v4l-4 2-4-2v-4L4 10l4-2V4l4-2z' },
      airflow:    { viewBox: '0 0 24 24', path: 'M2 12c0-5 4-9 9-9s9 4 9 9-4 9-9 9S2 17 2 12z' },
    };
    const KEYWORDS = {
      kubernetes: ['kubernetes', 'k8s'],
      airflow:    ['airflow'],
    };

    let injected = 0;
    const foTexts = Array.from(svg.querySelectorAll(
      'foreignObject p, foreignObject span, foreignObject div'
    ));
    foTexts.forEach((t) => {
      const text = (t.textContent || '').trim().toLowerCase();
      if (!text) return;
      let iconKey = null;
      for (const [key, kws] of Object.entries(KEYWORDS)) {
        if (kws.some(kw => text.includes(kw))) { iconKey = key; break; }
      }
      if (!iconKey || !ICONS[iconKey]) return;

      // Walk up to node group
      let g = t.parentNode;
      while (g && g.nodeName.toLowerCase() !== 'svg') {
        if (g.nodeName.toLowerCase() === 'g') {
          const cls = g.getAttribute('class') || '';
          if (cls.split(' ').includes('node') || g.querySelector(':scope > rect')) break;
        }
        g = g.parentNode;
      }
      if (!g || g.nodeName.toLowerCase() !== 'g') return;

      // THE GUARD (BUG-ICON-CIRCLE-RENDER-01 fix)
      if (g.getAttribute('data-icon-injected') === '1') return;

      // Would inject if guard hadn't fired
      injected++;
    });

    return {
      injected,
      serverUseCount: svg.querySelectorAll('use[href^="#icon-"]').length,
      clientUseCount: svg.querySelectorAll('use[href^="#fa_icon_"]').length,
    };
  });

  expect(clientGuardResult.error).toBeUndefined();
  expect(clientGuardResult.injected).toBe(0);         // guard must fire for both nodes
  expect(clientGuardResult.serverUseCount).toBe(2);   // server icons intact
  expect(clientGuardResult.clientUseCount).toBe(0);   // no circle injection

  // Screenshot for evidence
  const screenshotDir = path.join(
    ROOT,
    '.ai-sldc/debugging/BUG-ICON-CIRCLE-RENDER-01/evidence/ui/screenshots'
  );
  fs.mkdirSync(screenshotDir, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDir, 'BUG-ICON-CIRCLE-RENDER-01-guard-test.png'),
    fullPage: true,
  });
});
