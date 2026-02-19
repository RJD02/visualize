# Story 01 Acceptance Criteria

Acceptance checklist:

 - The intermittent icon rendering artifact can be reproduced reliably in a local, deterministic harness.
 - A minimal code/configuration change is proposed and implemented only within the renderer/export scope.
 - Unit tests and a small integration test (headless) demonstrate the artifact is resolved and prevent regressions.
 - No changes are made outside of the allowed scope (no unrelated refactors in `src/` beyond the renderer files).
 - Tests pass locally (unit) and headless Cypress (if applicable) in CI config.

Verification steps:

 1. Run included reproduction script to reproduce artifact.
 2. Run unit tests; they must pass.
 3. Run integrated export verification; output assets must match the golden baseline.
# Acceptance Criteria – STORY-ICON-001

## Functional Criteria

1. When diagram contains "postgres":
   - Output SVG contains postgres icon SVG element
   - Icon visible in rendered UI

2. When diagram contains "kafka":
   - Kafka icon embedded
   - Positioned correctly relative to node

3. When diagram contains "minio":
   - MinIO icon embedded

4. Unknown service:
   - No icon injected
   - No runtime error

---

## Technical Criteria

1. SVG remains valid XML
2. No console errors in browser
3. No layout overlap between:
   - Icon
   - Node label
   - Edge connectors
4. Icons injected only once per node

---

## Cypress Automation Criteria

The following automated tests must pass:

### 1. Icon Rendering Test
- Visit diagram page
- Load diagram containing postgres
- Assert SVG contains postgres icon selector

### 2. Multi-Icon Test
- Load diagram containing postgres + kafka + minio
- Assert all 3 icons present

### 3. Headless Execution
- Cypress must pass in headless mode
- No flaky timing issues

### 4. DOM Validation
- Icon element exists inside expected node container
- No duplicate icon injection

### 5. Snapshot Stability
- SVG snapshot matches expected structure

---

## Completion Definition

Story is complete only if:

- Plan approved
- Implementation complete
- Unit tests pass
- Cypress tests pass
- Audit report generated
- state.json updated to completed