# PLAN-BUG-BLUE-DOT-01
# Draft Plan — Fix Blue-Dot Icon Rendering + Regression Guard

**Entity ID:** BUG-BLUE-DOT
**Kind:** debug
**Branch:** feature/BUG-BLUE-DOT
**Plan ID:** PLAN-BUG-BLUE-DOT-01

---

## 1. Problem Understanding

Architecture diagram nodes for known technology services (Kafka, Postgres, Kubernetes,
etc.) rendered as **blue filled circles** in both the browser UI and PNG exports.

Two layers of code contribute:

### Server-side (`src/diagram/icon_injector.py`)

`inject_icons()` uses a generic fallback symbol when `resolve_icon_key(label)` returns
`None` or when the actual icon SVG file cannot be found:

```python
_GENERIC_SYMBOL_PATH = "M12 2a10 10 0 100 20A10 10 0 0012 2zm0 2a8 8 0 110 16A8 8 0 0112 4z"
```

The CSS class `generic-icon` applies `fill: #1e40af` → **solid blue circle**.

Additionally, `_read_icon_svg(fname)` falls back to `placeholder.svg`, and if that
is also absent, an empty `ET.Element("svg")` is used — but the symbol is still
registered, so the `<use>` element renders with the generic-circle style.

### Client-side (`ui/src/diagram/iconRegistry.js`)

The `ICONS` map uses simplified geometric paths. Several are visually circular:

```js
kafka:   'M4 12a8 8 0 1116 0 8 8 0 01-16 0zm2 0h12'  // circle with horizontal line
airflow: 'M2 12c0-5 4-9 9-9s9 4 9 9-4 9-9 9S2 17 2 12z'  // closed circle
```

CSS `.node-icon { fill: #1e40af }` makes these look like blue dots.

### Interaction between layers

`iconRegistry.js` has a guard (`data-icon-injected="1"`) that should prevent
client-side icons overriding server-side ones.  If server-side injection succeeds
for a known service, client-side is skipped → correct brand SVG shows.  If server-side
fails or skips a node (ID mismatch, missing file), client-side falls back to its
simplified-geometry icon → blue dot.

---

## 2. Fix Status

Commit `ef3e544` claims to fix the primary issue: "fix(icons): brand icons render as
real SVG logos not blue circles."

**This plan verifies the fix and adds regression protection.**

---

## 3. Reproduction Harness

Before testing the fix, the plan includes a lightweight reproduction test:

### Cypress (`cypress/e2e/bug_blue_dot_regression.cy.js`)

Uses `cypress/fixtures/diagram_postgres.html` (already exists) and a new
`diagram_kafka.html` fixture to:
1. Mount a minimal SVG containing a "Kafka" node
2. Enable `window.ENABLE_SVG_ICON_INJECTION = true`
3. Call `postProcessSvgWithIcons()`
4. Assert: no `<path>` element with the known generic-circle `d` attribute exists
5. Assert: the `<use>` element references a symbol with >1 child element OR a
   `viewBox` that is not `0 0 24 24` with only a single circular path

### Unit test addition (`tests/unit/test_icon_injector.py` — extend)

Add:
- `test_known_service_does_not_use_generic_circle_symbol`: inject "Kafka" node →
  assert resulting SVG does NOT contain the generic circle path
- `test_unknown_service_uses_non_blue_circle_fallback`: inject "MyUnknownService" →
  assert symbol is either absent OR uses a non-filled-circle path (not `_GENERIC_SYMBOL_PATH`)
- `test_resolve_icon_key_covers_all_mapping_keys`: every key in `MAPPING` has at
  least one keyword that resolves to it
- `test_inject_idempotent`: calling `inject_icons()` twice on the same SVG does not
  duplicate `<use>` elements

---

## 4. Fix Scope

### If `ef3e544` is verified complete: add regression tests only

| File | Change |
|------|--------|
| `tests/unit/test_icon_injector.py` | Add 4 regression unit tests |
| `cypress/e2e/bug_blue_dot_regression.cy.js` | New Cypress E2E regression spec |
| `cypress/fixtures/diagram_kafka.html` | New fixture for Kafka node test |

### If `ef3e544` is incomplete: also patch

| File | Change |
|------|--------|
| `src/diagram/icon_injector.py` | Replace `_GENERIC_SYMBOL_PATH` with a non-circle path; or suppress generic injection entirely |
| `ui/src/diagram/iconRegistry.js` | Update `kafka` and `airflow` paths to non-circle shapes |

---

## 5. File-Level Change Scope

### Always-changed (regression guard)
- `tests/unit/test_icon_injector.py` — extend with 4 tests
- `cypress/e2e/bug_blue_dot_regression.cy.js` — NEW
- `cypress/fixtures/diagram_kafka.html` — NEW

### Conditionally changed (if fix is incomplete)
- `src/diagram/icon_injector.py`
- `ui/src/diagram/iconRegistry.js`

### SDLC artifacts
- `.ai-sldc/debugging/BUG-BLUE-DOT/plans/PLAN-BUG-BLUE-DOT-01.draft.md` — this file
- `.ai-sldc/debugging/BUG-BLUE-DOT/plans/PLAN-BUG-BLUE-DOT-01.locked.json` — on approval
- `.ai-sldc/debugging/BUG-BLUE-DOT/logs/planning.log`

---

## 6. Test Plan

### Execution Order

1. Run unit tests: `pytest tests/unit/test_icon_injector.py -v`
2. Run Cypress headless: `npx cypress run --spec cypress/e2e/bug_blue_dot_regression.cy.js`

### Unit Test Cases

| Test | Expected |
|------|---------|
| `test_known_service_does_not_use_generic_circle_symbol` | No generic circle path in SVG |
| `test_unknown_service_uses_non_blue_circle_fallback` | No `_GENERIC_SYMBOL_PATH` in SVG |
| `test_resolve_icon_key_covers_all_mapping_keys` | All 30 MAPPING keys resolve via KEYWORDS |
| `test_inject_idempotent` | Calling inject_icons() twice → same count of `<use>` elements |

### Cypress E2E Cases

| Test | Expected |
|------|---------|
| `BUG-BLUE-DOT: kafka node does not render as blue circle` | No generic-circle `<path d>` in rendered SVG |
| `BUG-BLUE-DOT: postgres node renders recognizable icon` | `<use>` references symbol with multiple child elements |
| `BUG-BLUE-DOT: unknown service does not render blue circle` | Either no icon or non-circle placeholder |

### Evidence Collection

- Screenshot: `BUG-BLUE-DOT-kafka-icon-<timestamp>.png`
- Screenshot: `BUG-BLUE-DOT-postgres-icon-<timestamp>.png`
- `run-meta.json` in `.ai-sldc/debugging/BUG-BLUE-DOT/evidence/ui/`

---

## 7. Acceptance Criteria Cross-Check

| Criterion | Coverage |
|-----------|---------|
| Known services show non-circle icon | Unit test + Cypress assertion |
| Unknown services do not show blue circle | Unit test + Cypress assertion |
| resolve_icon_key covers all supported keywords | Unit test |
| inject_icons is idempotent | Unit test |
| No console errors from icon injection | Cypress `cy.on('uncaught:exception', ...)` guard |
| Download PNG / SVG unaffected | Existing tests not broken |
| Confidence ≥ 0.85 | Review gate |

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| `ef3e544` only partially fixed server-side; client-side still blue dots | Cypress test catches this via DOM assertion on `<path d>` content |
| Real brand SVG files have complex paths that break `canvas.toBlob()` | Export tests run independently; PNG export has its own test |
| Fixtures become stale if node IDs change | Fixtures use data-service attribute + label text, not internal IDs |

---

## 9. Rollback Strategy

Regression tests are purely additive.  If a source fix is needed and breaks
something, `git revert` the source change.  Tests remain to guard the fixed state.
