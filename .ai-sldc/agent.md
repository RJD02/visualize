# -------------------------------------------------------------------
# SECTION: Autonomous Governed SDLC + Debug Engine (Decision + Audit Mode)
# -------------------------------------------------------------------

This section EXTENDS the existing Agent Execution Protocol.
It does NOT replace prior Git discipline rules.

All Git rules (branching, commit hygiene, PR discipline) still apply.
This section governs HOW work is executed.

---

# 1) Governing Mode

The agent operates in:

FULLY AUTONOMOUS GOVERNED MODE

Non-negotiable priority order:

1. Meet Acceptance Criteria (story or bug)
2. All tests pass (unit + Cypress headless)
3. Reproduce and permanently fix issue (for debug)
4. Preserve determinism
5. Full auditability & explainability

The agent MUST:
- Make autonomous decisions
- Persist all workflow state in repository artifacts
- Never rely on conversation memory
- Never silently deviate from plan

---

# 2) Workflow Types

Workflow is determined by:

.ai-sdlc/state.json

{
  "kind": "feature" | "debug",
  "id": "<STORY-ID or BUG-ID>",
  "phase": "<current-phase>"
}

Valid kinds:
- feature
- debug

---

# 3) Valid Phases (Exactly One Per Invocation)

- planning
- awaiting_approval
- approved
- execution
- testing
- review
- completed
- failed

The agent MUST:
- Execute exactly ONE phase per invocation
- Persist state.json before exit
- Never skip a phase
- Never re-run a completed phase

---

# 4) Required Artifact Structure

## For FEATURE Workflow

.ai-sdlc/stories/<STORY-ID>/
  - intent.md
  - acceptance.md

.ai-sdlc/plans/
  - PLAN-<ID>.draft.md
  - PLAN-<ID>.locked.json

.ai-sdlc/audits/
  - AUDIT-<ID>.md
  - deviations.log

.ai-sdlc/logs/
  - execution.log

---

## For DEBUG Workflow

.ai-sdlc/debugging/<BUG-ID>/
  - intent.md
  - reproduction.md
  - acceptance.md
  - evidence/

Plus same plan, audit, logs structure as feature.

---

# 5) Logging & Explainability (MANDATORY)

All decisions MUST append structured logs to:

.ai-sdlc/logs/execution.log

Each log entry MUST include:

- timestamp
- kind (feature/debug)
- id
- phase
- action
- reason
- outcome
- next_state

Deviation events MUST be written to:

.ai-sdlc/audits/deviations.log

Deviation types include:
- PLAN_CHANGE
- ENVIRONMENT_FIX
- INFRA_BOOTSTRAP
- TEST_STRATEGY_ADJUSTMENT
- FALLBACK_BEHAVIOR

No silent deviation is permitted.

---

# 6) Environment Self-Repair Rules

If required environment is missing:

The agent MUST autonomously:

- Add minimal deterministic configuration
- Install missing dev dependencies
- Add minimal package.json scripts
- Bootstrap Cypress config if missing
- Prefer local fixtures over internet resources
- Avoid CDN dependency during tests
- Ensure Cypress runs headless

All environment changes MUST:
- Be logged as ENVIRONMENT_FIX
- Recorded in deviations.log (if not in plan)

Determinism is mandatory.

---

# 7) Planning Phase

Condition:
state.phase == "planning"

Agent MUST:

1. Load intent + acceptance (+ reproduction for debug)
2. Produce PLAN-<ID>.draft.md containing:

   - Problem understanding
   - Suspected root causes (debug only)
   - Proposed fix
   - File-level change scope
   - Test plan (unit + Cypress)
   - Reproduction automation plan (debug)
   - Risks
   - Rollback strategy

3. Update state.phase → awaiting_approval
4. Log PLAN_CREATED
5. Exit

During planning:
- src/ and tests/ MUST NOT be modified

---

# 8) Approval → Auto-Lock

Condition:
state.phase == "approved"
AND draft exists
AND locked.json missing

Agent MUST:

1. Convert draft → PLAN-<ID>.locked.json
2. Include:

   {
     "plan_id": "",
     "kind": "",
     "entity_id": "",
     "allowed_scope": [],
     "tasks": [],
     "constraints": [],
     "acceptance_summary": "",
     "draft_checksum": ""
   }

3. Update state.phase → execution
4. Log PLAN_LOCKED
5. Exit

No implementation allowed during this phase.

---

# 9) Execution Phase

Condition:
state.phase == "execution"
AND locked.json exists

Agent MUST:

- Modify ONLY allowed_scope files
- Implement minimal permanent fix
- For debug:
  - Implement reproduction harness first if missing
- Add or update tests
- Preserve determinism
- Avoid refactoring outside scope
- Update state.phase → testing
- Log IMPLEMENTATION_COMPLETE
- Exit

---

# 10) Testing Phase (Strict Enforcement)

Condition:
state.phase == "testing"

Execution order:

1. Run unit tests
2. Run Cypress headless tests

For DEBUG workflow:
- Must include reproduction test
- Must include regression guard

If tests fail:

- Fix
- Re-run
- Maximum 3 cycles

If blocked by missing Cypress config/deps:

- Bootstrap minimal config
- Log ENVIRONMENT_FIX
- Retry

If after 3 cycles still failing:

- state.phase → failed
- Generate failure audit
- Log FAILURE
- Exit

If all tests pass:

- state.phase → review
- Log TESTS_PASSED
- Exit

---

# 11) Review Phase

Condition:
state.phase == "review"

Agent MUST:

- Validate acceptance.md explicitly
- Cross-check checklist
- Summarize unit + Cypress output
- Save evidence for DEBUG into evidence/
- Generate AUDIT-<ID>.md with:

  - Summary of changes
  - Why change was required
  - Test results
  - Acceptance checklist verification
  - Deviations
  - Confidence score (0.0–1.0)

If confidence >= 0.85:
  state.phase → completed

Else:
  state.phase → execution

Always log REVIEW_RESULT.

Exit after updating state.

---

# 12) Restart Safety

On every invocation:

- Read state.json
- Resume exact phase
- Never repeat completed phase
- Never rely on chat memory
- Trust repository state only

---

# 13) Decision Policy

The agent MUST NOT stop to ask:

"What should I do?"

Decision rules:

- Prefer deterministic local setup
- Prefer adding Cypress tests over manual verification
- Prefer minimal config bootstraps
- Prefer smallest possible permanent fix
- Never bypass tests
- Never weaken acceptance criteria
- Never reduce determinism

---

# 14) Git Integration (Binding Rule)

This Autonomous SDLC mode operates within Git discipline:

For each story/bug:

- Create feature/<id> branch
- Commit only relevant files
- Include:
  - plan files
  - audit files
  - logs
  - modified source/tests
- Never commit execution.log noise unrelated to story

Before PR:

- Ensure:
  - state.phase == completed
  - audit generated
  - tests passed

PR description MUST include:
- Acceptance checklist
- Test results
- Confidence score
- Deviations summary

---

END OF GOVERNED MODE EXTENSION