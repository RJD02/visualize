# PLAN-BUG-ICON-01 (DRAFT)

Plan ID: PLAN-BUG-ICON-01
Related Bug: BUG-ICON-01
Kind: debug

Date: 2026-02-19
Phase: draft

## Summary / Problem Understanding

Users report that service icons injected into generated SVG diagrams are not appearing consistently, or the injector sometimes places duplicate icons or invalid references. This debugging plan targets reproducing the failure, identifying the root cause, and implementing the smallest reliable fix with tests to prevent regressions.

Relevant artifacts:
- `.ai-sldc/debugging/BUG-ICON-01/intent.md`
- `.ai-sldc/debugging/BUG-ICON-01/reproduction.md`
- Implementation: `src/diagram/icon_injector.py` (existing)

## Suspected Root Causes

1. Mapping fallback behavior creates symbol ids that collide (e.g., unknown token -> `icon-unknown-service`) causing duplicate symbols and unexpected references.
2. Injector uses `use` with `href` attribute which may be namespace-sensitive (`xlink:href` vs `href`) leading to invalid references in some environments.
3. Idempotence marker (`data-icon-injected`) may not be set or detected correctly due to attribute namespace or element selection mismatch, leading to duplicate injections.
4. Sanitizer may remove attributes needed for symbol/viewBox, causing rendering issues.

## Proposed Fix (high-level)

- Ensure canonical symbol ids are deterministic and limited to a known set. For unknown services, always use a single `icon-service-generic` symbol.
- Use both `href` and `xlink:href` attributes on `<use>` elements to maximize compatibility.
- Strengthen idempotence check: when injecting, check for both `data-icon-injected` and presence of a `<use>` child referencing the symbol; avoid double injection.
- Improve sanitizer to preserve `viewBox` and necessary attributes while stripping dangerous attributes.

## File-level Modifications (planned)

- `src/diagram/icon_injector.py` — modify injector to canonicalize symbol ids, set both `href` and `xlink:href`, improve idempotence checks, and tighten sanitizer.
- `tests/unit/test_icon_injector.py` — add regression tests reproducing the bug scenarios (duplicate injection, unknown token fallback, `href` vs `xlink:href`).
- `cypress/fixtures/*` — add a failing reproduction fixture if needed (for repro harness).
- `cypress/integration/icon_injection.spec.js` — add a Cypress repro test (if not already present) that fails before fix and passes after.

Note: No modification to files outside locked scope until plan is approved and locked.json created.

## Reproduction Automation Plan

1. Create unit test that simulates injecting into an SVG where node already has `data-icon-injected` or existing `<use>` and assert injector does not add another `<use>`.
2. Create unit test for unknown token that verifies fallback uses `icon-service-generic` only.
3. Create Cypress test that loads fixture with multiple nodes and verifies no duplicate icons and that `<use>` references resolve (file-based assertions can be used to avoid network requirements).

## Test Plan

Unit tests:
- Duplicate injection prevention (simulate two successive calls)
- Unknown token fallback canonicalization
- `href` vs `xlink:href` presence on injected `<use>` element

Cypress tests:
- Reproduction test: load fixture HTML and assert no duplicate `data-icon-injected` markers and `use` hrefs point to valid symbol ids

Acceptance for debug:
- Reproduction test fails on current code and passes after fix (for debug workflow)
- All unit tests pass
- Cypress headless tests pass

## Risks and Rollback

- Risk: Changes to sanitizer might inadvertently preserve unsafe attributes. Mitigation: keep whitelist conservative and unit-test sanitizer behavior.
- Risk: Changing `use` attributes may not affect all browsers; fallback cloning remains available.

Rollback plan:
1. Revert the injector changes (git revert implementation commits)
2. Re-enable previous behavior via feature flag if available

## Next Steps (after approval)

1. Convert draft to locked.json and set state to `execution`.
2. Implement minimal injector fixes in `src/diagram/icon_injector.py`.
3. Add unit tests & cypress repro test.
4. Run unit + Cypress tests and iterate until passing.

Prepared by: autonomous debug agent
