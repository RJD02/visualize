# BUG-COPY-PNG-STUCK-01
# Copy PNG Stuck in "Processing..." and Does Not Copy to Clipboard

## Problem

When clicking "Copy PNG", the UI becomes stuck showing "Processing..." and the PNG is not copied to clipboard.
The user cannot complete the copy action.

Screenshot evidence indicates UI remains in processing state indefinitely.

---

## Expected Behavior

- Clicking "Copy PNG" should:
  - generate PNG from current diagram
  - copy it to clipboard successfully
  - show a success state/toast
  - exit processing state deterministically within a reasonable time

---

## Suspected Causes

- Clipboard API not available in environment (secure context requirement)
- Promise never resolves/rejects (missing finally)
- Error swallowed and UI state never reset
- PNG generation pipeline hangs on large diagrams
- Browser permissions issue not handled
- Async race between export and UI state

---

## Debug Approach

- Add Playwright reproduction test:
  - click Copy PNG
  - wait for processing state to finish
  - validate clipboard write success OR expected failure message
  - capture screenshot/video on failure

- Ensure UI always exits processing state:
  - success → reset button state
  - failure → show error + reset state

- Store evidence logs and screenshots.

---

## Constraints

- Must be deterministic
- Must not break Download PNG workflow
- Must not rely on external services