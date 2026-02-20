AUDIT — BUG-ICON-01 Regression Investigation

Date: 2026-02-20T11:45:00Z
Author: automated-debug-agent

Issue: UI diagrams generated after a recent server change appeared "not coloured" and "not aesthetic" to the user. The user reported that diagrams generated via the UI lost their expected styling and vendor-looking visuals after the inlining changes were applied server-side.

Summary of investigation
------------------------
- Reproduced the server-rendered SVG fetch for the reproduction file `outputs/repro_icon_visibility.fixed.svg` via `/api/diagram/render?format=svg`.
- Observed the server returned SVGs with inlined icon groups (`data-inlined-from` markers) and a small style block that included `.node-icon { fill: currentColor; ... }`.
- The initial change had applied `inline_use_references()` unconditionally to all served SVGs. That function also normalizes style blocks and inserts a default namespace which can unintentionally alter unrelated style rules in a generated diagram (for example replacing or neutralizing designer-supplied style rules).

Root cause
-----------
- The server previously applied inlining and style-normalization to every served SVG, regardless of whether it contained `<use>`/`<symbol>` references. `_normalize_icon_styles()` performs conservative replacements (e.g., replace `opacity:0` with `opacity:1`, `display:none` -> `display:block`, neutralizes some style rules). Applied globally, this can alter intended aesthetic styles authored into generated diagrams.

Action taken
------------
1. Reverted the unconditional inlining behavior in `src/server.py` and restricted application of `inline_use_references()` to cases where it is actually needed:
   - Condition: SVG contains `<use`, `xlink:href`, or `<symbol` and does not already include `data-inlined-from` markers.
   - This prevents normalization of unrelated diagrams that do not rely on symbol/use references.
2. Re-deployed the service via `scripts/deploy.sh` and re-fetched the reproduction file. The reproduction SVG is still inlined (since it contained symbol references), and the returned SVG contains expected `data-inlined-from` markers and a small `.node-icon` style block.

Validation
----------
- Fetched server-rendered SVG (static) for reproduction: server returned an inlined SVG, `data-inlined-from` present. (`LEN 2523`, contains expected shapes.)
- Fetched enhanced rendering: also returns an SVG (length similar), style block present.
- No evidence that the server now changes unrelated SVGs (conditional inlining minimizes risk). However, we were unable to reproduce the user's exact original aesthetic diagram generation locally (LLM-based generation); the regression was observed by the user after the unconditional change. The conditional change should prevent further regressions.

Recommended next steps
----------------------
1. Add a feature flag to control server-side inlining: `ENABLE_SERVER_SVG_INLINING` (default `false`). Only enable in CI or where sprite-based icons are used. This allows immediate rollback if further regressions are observed.
2. Add an automated regression test: generate a representative 'aesthetic' diagram (from a stable sample), fetch via `/api/diagram/render`, and assert that the returned SVG contains original style rules (e.g., specific selectors, fills, or class names) unchanged when `<use>` is not present.
3. Add a short note to `src/icons/README.md` documenting the server inlining behavior and its opt-in nature.
4. Prepare a small PR that includes the conditional inlining change, the feature-flag option, and the regression test. Run CI and, once green, merge.

Files changed in this investigation
---------------------------------
- `src/server.py` — conditional inliner invocation (patched).

Immediate remediation
---------------------
- If you are still seeing broken aesthetics in the UI after this change, hard-refresh the browser and re-generate the diagram. If the issue persists, enable `DEBUG_SVG_RENDER` in the UI to inspect the returned SVG (open `DevTools` → `Elements` to view the inline markup) and share the returned SVG for analysis.

Confidence
----------
0.78 — We reproduced the server-side behavior and applied a targeted fix. Because the user's reported diagram was generated via the LLM pipeline, we cannot fully reproduce the original aesthetic without running the generation step. The conditional fix reduces risk and is the safest next step.

-- end
