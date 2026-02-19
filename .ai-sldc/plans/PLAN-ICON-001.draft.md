# PLAN-ICON-001 (DRAFT)

Plan ID: PLAN-ICON-001
Related Story: STORY-ICON-001 ([intent](.ai-sldc/stories/story-01/intent.md) / [acceptance](.ai-sldc/stories/story-01/acceptance.md))

Date: 2026-02-19
Phase: draft

## Summary

Enable deterministic, offline-safe inline SVG icon injection for known services (postgres, kafka, minio) when the diagram agent renders SVG output. This is a planning-stage document only — no code changes will be made in this phase.

Inputs:
- ` .ai-sldc/stories/story-01/intent.md`
- ` .ai-sldc/stories/story-01/acceptance.md`

## Architecture Changes (high-level)

- Add a dedicated icons asset area (read-only at runtime): `ui/icons/` (store canonical SVGs checked into repository). This is a proposed file-level change — not performed in planning.
- Introduce an injection layer inside the diagram render pipeline responsible for: locating node types, resolving icon mapping, sanitizing SVG content, and inserting icon <symbol> or inline SVG into node group.
- Prefer a small, deterministic `icon-injector` module adjacent to the diagram renderer (name proposal: `src/diagram/icon_injector.py` or `ui/js/iconInjector.js` depending on renderer language). This will expose a single pure function for mapping+injection to make unit testing straightforward.
- Keep diagram generation core code unchanged; wire injection behind a feature-flag/config toggle so rollout can be controlled.

File-level modifications (planned, not implemented here):
- `ui/icons/*.svg` — canonical SVG files for each supported service
- `src/diagram/icon_injector.py` (or `ui/js/iconInjector.js`) — injection logic and mapping table
- `src/diagram/render_pipeline.py` — small hook points to call injector (feature-flag guarded)
- `tests/unit/test_icon_injector.py` — unit tests for mapping and sanitization (planned)
- `cypress/integration/icon_injection.spec.js` — end-to-end tests (planned)

## SVG Injection Strategy

Goals: deterministic, offline, safe, performant, accessible.

Approach options considered:
- Inline SVG per node (preferred): insert SVG nodes directly into the node's <g> so styles and transforms apply naturally. Pros: no extra network requests, easy to style, deterministic. Cons: larger SVG output size.
- SVG <symbol> sprite + <use>: maintain a <defs> sprite once per document and reference with `<use>`. Pros: reduced duplication. Cons: `<use>` behavior cross-browser for external resources can be tricky; inline sprite in same SVG is acceptable.

Chosen strategy (hybrid):
- At render time, create or update a document-level `<defs id="icon-sprite">` containing `<symbol id="icon-{name}">` for each icon used in the diagram. For each node, insert a small `<use xlink:href="#icon-{name}" ...>` or clone the symbol inline if runtime requires independent attributes. The injector will prefer `<use>` referencing local `<symbol>` for size/performance, and fall back to cloning inline for maximum compatibility in environments where `<use>` is unreliable.

Safety and sanitization:
- All composite SVGs will be sanitized server-side to remove scripts, external references, and inline event handlers prior to insertion.
- Only allow a whitelisted set of tags/attributes. Use a conservative sanitizer library or a small custom sanitizer that strips disallowed attributes (`on*`, `script`, `foreignObject`, `xlink:href` to external URLs, etc.).

Accessibility:
- Ensure `role="img"` and `aria-label` or `title` are provided on icon elements where appropriate.

Performance:
- Generate the `<defs>` sprite once per document render. Reuse symbols via `<use>` to avoid duplicating large SVG markup when supported.

## Icon Mapping Table (deterministic)

| Logical name | Service match / input token | Filename (proposed) | Fallback |
|---|---:|---|---|
| postgres | postgres, postgresql | ui/icons/postgres.svg | ui/icons/service-generic.svg |
| kafka | kafka | ui/icons/kafka.svg | ui/icons/service-generic.svg |
| minio | minio | ui/icons/minio.svg | ui/icons/service-generic.svg |
| database | db, database | ui/icons/database.svg | ui/icons/service-generic.svg |
| cache | redis, memcached | ui/icons/cache.svg | ui/icons/service-generic.svg |

Mapping rules:
- Matching should be case-insensitive and perform token normalization (strip punctuation). Exact string token match is required (no fuzzy or probabilistic mapping).
- If multiple tokens appear for a node, use the first matching supported service token following a deterministic precedence list (postgres -> kafka -> minio -> database -> cache).

## Test Strategy

Principles: test deterministically, with fixtures that run offline, and verify both structure and rendering behavior.

Unit tests (fast, isolated):
- Validate mapping table: given input node metadata (e.g., `{type: 'postgres'}`) the injector resolves to `postgres.svg`.
- Sanitizer tests: supply SVG samples with unsafe attributes and assert sanitizer removes unsafe content while preserving structure.
- Injection API tests: given a small SVG document fixture, call the injector and assert:
  - `<defs id="icon-sprite">` created when icons used
  - `<use>` or inline nodes are inserted into the correct node `<g>`
  - No duplicate symbol entries for repeated icon usage

Tools/language: write pure unit tests in the same language as the injector. For Python: `pytest`. For JS: `jest` or `mocha` (project currently uses Python but Cypress implies JS; exact choice deferred to implementation).

End-to-end tests (Cypress):
- Headless Cypress runs (CI) covered tests derived from acceptance criteria:
  1. Icon Rendering Test (postgres) — assert selector for postgres icon exists in rendered SVG
  2. Multi-Icon Test (postgres + kafka + minio) — assert all 3 icons present and unique
  3. No Duplicate Injection — ensure each node has at most one icon child element
  4. Console Error Check — assert no browser console errors during test
  5. Snapshot Stability — perform deterministic SVG snapshot comparison of the rendered SVG structure

Test data: static diagram fixtures containing labeled nodes (postgres, kafka, minio). Tests must run offline and not fetch external resources.

CI configuration:
- Cypress run command: `cypress run --headless` (documented in plan; actual CI wiring in execution phase)

## Risk Analysis

- Risk: SVG-based XSS or script injection.
  - Impact: high. Mitigation: strict sanitizer, repository-only icons, remove `on*` attributes and disallow `foreignObject` and `<script>`.

- Risk: Duplicate icons causing layout overlap.
  - Impact: medium. Mitigation: injector ensures idempotence — a marker attribute (`data-icon-injected`) on node `<g>` prevents repeated injection.

- Risk: Browser `<use>` rendering inconsistencies in some headless environments.
  - Impact: medium. Mitigation: fall back to cloning inline symbol for headless runners or add small compatibility shim in tests.

- Risk: Increased SVG size and performance degradation.
  - Impact: low to medium. Mitigation: use `<symbol>` + `<use>` where possible; keep icons small and optimized (svgo) in `ui/icons`.

- Risk: Missing icon file.
  - Impact: low. Mitigation: fall back to `service-generic.svg` and log a non-failing warning; acceptance requires no runtime error.

## Rollback Plan

If the feature causes regressions in rendering or tests fail during execution/testing phases, rollback options:

1. Feature-flag toggle: disable icon injection via configuration (primary rollback path). This avoids code reverts.
2. Revert commit(s) that added injector and icons (if flag unavailable). Use git revert on the implementation commits listed in the locked plan.
3. Restore previous SVG output snapshots (CI) and re-run acceptance criteria tests.

Rollback runbook (operator steps):
- Set configuration `ICON_INJECTION=false` in runtime config and redeploy rendering service.
- If deployment does not remove problem, perform `git revert <commit>` of the locked plan commits and redeploy.

## Acceptance Criteria Mapping

- All acceptance items in ` .ai-sldc/stories/story-01/acceptance.md` must map to unit + cypress tests.
- The plan targets deterministic mapping and offline behavior required by acceptance.

## Next Steps (upon plan approval)

1. Lock plan: produce `PLAN-ICON-001.locked.json` containing file-level changes and checksums.
2. Implement `icon_injector` module behind a feature flag.
3. Add `ui/icons/*.svg` assets and run `svgo` to optimize.
4. Add unit tests and Cypress tests as specified.
5. Run CI: unit tests then `cypress run --headless`.

---

Prepared by: planning agent
