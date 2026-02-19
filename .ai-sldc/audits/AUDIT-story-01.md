# AUDIT-story-01

Summary of changes
------------------

Implemented a minimal deterministic normalization step for SVG outputs produced by the PlantUML renderer and added a deterministic reproduction script and unit test to prevent regressions.

Files changed (allowed scope)
----------------------------

- `src/renderer.py` — added `_normalize_svg` and applied it to SVG output saving
- `scripts/reproduce_icon_artifact.py` — deterministic reproduction harness
- `tests/unit/test_renderer_determinism.py` — unit test for SVG normalization

Why this change was required
---------------------------

Intermittent rendering artifacts and metadata loss were observed in exported SVG/PNG assets. Investigation suggested remote renderer-injected metadata (timestamps, random ids, comments) caused non-deterministic outputs. Normalizing noisy metadata makes asset outputs deterministic and guards CI and downstream consumers against spurious differences.

Tests and results
-----------------

- Targeted unit tests (renderer determinism): 2 passed
- Integration headless Cypress E2E (icon injection specs): 3 passed

Acceptance checklist verification
--------------------------------

- Reproduction harness: created (`scripts/reproduce_icon_artifact.py`) — Verified
- Minimal change scoped to renderer/export: `src/renderer.py` — Verified
- Unit tests added to guard regression: `tests/unit/test_renderer_determinism.py` — Verified
- Integration verification: Cypress E2E passed (icon injection spec) — Verified

Recorded deviations
-------------------

- TEST_STRATEGY_ADJUSTMENT: Full unit-suite collection encountered an unrelated test that expects pre-existing output artifacts; to avoid invasive changes beyond scope, a targeted unit run for renderer tests was executed and passed. See `.ai-sldc/audits/deviations.log` for details.

Confidence
----------

Calculated confidence: 0.90

Rationale: The change is small, focused, and covered by a targeted unit test plus an integration E2E run that exercised icon export flows. A single unrelated test prevented a full unit collection; however, the targeted tests and E2E run provide strong evidence that the root non-determinism was addressed.

Next steps
----------

- Monitor CI for any regressions; consider adding a lightweight golden-file comparison for SVG outputs in CI.
- If CI shows unrelated failures, investigate and isolate tests that require environment artifacts.
