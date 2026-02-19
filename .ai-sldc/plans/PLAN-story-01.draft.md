# PLAN-story-01.draft.md

Problem understanding
---------------------

Users observe intermittent rendering artifacts (missing metadata or visual glitches) when exporting icons from the `icons` worktree. The issue appears non-deterministic across runs and CI jobs.

Suspected root causes
---------------------

- Race condition or non-deterministic ordering in the export pipeline.
- Missing explicit deterministic configuration for the renderer (e.g., random seed, rendering flags).
- Asset post-processing step that strips or reorders metadata.

Proposed fix
------------

1. Add a deterministic reproduction harness for the icon export (small script under `.ai-sldc/debugging/` or `scripts/`) that produces the artifact deterministically.
2. Inspect renderer config; enforce deterministic flags (e.g., fixed seed, stable sort ordering for layers or attributes).
3. If metadata is stripped, ensure export preserves required metadata and update the exporter to do so.

File-level change scope
-----------------------

Allowed scope (minimal):

- `src/renderer.py` (or equivalent renderer module in `src/`) — adjust configuration handling.
- `scripts/` — add deterministic reproduction script.
- `.ai-sldc/` — plan, logs, tests harness files.

Not allowed: broad refactors elsewhere in `src/` or unrelated modules.

Test plan (unit + headless)
---------------------------

- Unit: Add targeted unit tests validating deterministic output of the renderer for a canonical input (compare serialized DOM/metadata or pixel-hash for PNG).
- Integration: Add a small headless verification script that runs export and compares produced assets against a golden baseline image/hash.
- Regression: Add the reproduction harness as a failing test initially, then it should pass after the fix.

Reproduction automation plan
----------------------------

Create `scripts/reproduce_icon_artifact.py` that runs the renderer with fixed inputs and outputs expected files. This script will be runnable locally and used in CI (simple Python script, no external network).

Risks
-----

- The root cause could be outside renderer (e.g., environment differences); mitigated by deterministic harness.
- Adding tests that depend on exact pixel hashes may be brittle; prefer vector/metadata checks where possible.

Rollback strategy
-----------------

- Keep changes minimal and isolated to renderer module. Revert the small commit if unexpected regressions appear; tests and reproduction harness will serve as quick detection.
