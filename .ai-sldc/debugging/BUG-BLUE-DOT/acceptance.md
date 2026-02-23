# BUG-BLUE-DOT
# Acceptance Criteria

## Fix Verification

[ ] Known services (postgres, kafka, kubernetes, redis, grafana, prometheus) render
    with recognizable, non-circular icon shapes.
[ ] Unknown services render with a visually neutral placeholder (NOT a blue filled circle).
[ ] No icon renders as a solid blue circle (fill:#1e40af circular path) for any
    node in the reference test diagram.

## Regression Guard

[ ] Unit test: `resolve_icon_key()` correctly matches all 30+ supported service keywords.
[ ] Unit test: `inject_icons()` with a known service produces a `<symbol>` with viewBox
    from the real SVG file (not the generic circular fallback path).
[ ] Unit test: `inject_icons()` with an unknown service renders the generic icon with
    a clearly non-circle placeholder shape OR omits the icon entirely.
[ ] Playwright/Cypress: diagram with "Kafka", "Postgres", "Kubernetes" nodes has
    no `<path d="M12 2a10 10 0 100 20...">` (generic circle) in the rendered SVG.
[ ] Playwright/Cypress: icon `<use>` elements reference symbols from real brand SVG files
    (symbol has child elements other than a single circle path).

## Non-regression

[ ] Icon injection for previously-working services is unaffected.
[ ] Download PNG / Download SVG still works.
[ ] No console errors from icon injection.

## Evidence

[ ] Screenshot evidence stored in `.ai-sldc/debugging/BUG-BLUE-DOT/evidence/ui/screenshots/`.
[ ] run-meta.json saved to evidence/ui/.
[ ] Confidence score ≥ 0.85.
[ ] PR review yields zero open feedback.
