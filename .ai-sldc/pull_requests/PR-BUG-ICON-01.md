Title: BUG-ICON-01 — Deterministic SVG icon injection fixes

Summary:
- Implemented canonical symbol IDs, unified `href` and `xlink:href` support, and idempotence checks in `src/diagram/icon_injector.py`.
- Added unit tests covering fallback generic symbol and idempotence (`tests/unit/test_icon_injector.py`).
- Bootstrapped Cypress config and minimal support files for headless E2E verification. Added fixtures used by tests.
- Created audits and logs under `.ai-sldc/` documenting plan, actions, deviations, and confidence.

Files of interest:
- src/diagram/icon_injector.py
- tests/unit/test_icon_injector.py
- cypress.config.js, cypress/support/e2e.js, cypress/fixtures/
- .ai-sldc/plans/PLAN-BUG-ICON-01.locked.json
- .ai-sldc/audits/AUDIT-BUG-ICON-01.md

Acceptance:
- All unit tests pass.
- Cypress headless E2E passes.
- Audit confidence >= 0.85.

Notes:
- A small embedded git worktree was accidentally committed at `.claude/worktrees/nice-brattain`; see `.ai-sldc/audits/deviation-2026-02-19-1145.log`.
- If you prefer the repo without `package.json`/Cypress dev files, I can revert those in a follow-up commit.

Requested reviewer actions:
- Review the audit and tests.
- Approve and merge when satisfied.
