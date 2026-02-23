# BUG-COPY-PNG-STUCK-01
# Acceptance Criteria

## Fix Behavior

[ ] Copy PNG completes successfully in supported environments.
[ ] If clipboard copy fails due to permissions/secure context, user sees a clear error message.
[ ] "Processing..." state always ends (success or failure) within a defined timeout (e.g., 10s).
[ ] Button state resets after completion.

## Automation & Evidence

[ ] Playwright test reproduces previous stuck behavior (pre-fix) and passes post-fix.
[ ] Evidence includes:
    - screenshot of processing state
    - screenshot of success/failure outcome
    - video/trace on failure
[ ] Logs capture:
    - start of copy
    - PNG generation duration
    - clipboard API result/error

## Regression

[ ] Download PNG still works.
[ ] Export SVG/Copy SVG unaffected.
[ ] Unit tests + Playwright tests pass.
[ ] PR review yields zero open feedback.
[ ] Confidence score ≥ 0.85.