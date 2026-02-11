# Codex Task: Align Planner → MCP → Audited Execution

## Context

You are working on a codebase located at:

/home/goku/dev/visualization

This system currently supports chat-driven diagram generation and styling, but execution paths are fragmented:
- heuristics exist outside the planner
- some MCP tools are invoked directly
- auditability is partial
- UI cannot reliably trace how outputs were produced

The goal is to **fully align the system to a Planner → MCP → Audited Execution architecture**.

---

## High-Level Goal

Every user request must flow through:

1) A single central planner (`ConversationPlannerAgent`)
2) The planner produces a structured, persisted plan
3) Each plan step is executed only via `mcp_registry.execute(...)`
4) Every execution produces auditable records
5) The UI can fetch and display the plan and its execution history

No shortcuts. No bypasses.

---

## Core Architectural Rules (Must Not Be Violated)

- Every user message produces a persisted `PlanRecord`
- All execution happens through MCP tools
- No internal service may call tools directly
- All special cases must be represented as planner steps
- Styling operations must return an `audit_id`
- All tool executions must be traceable to a `plan_id`

---

## Required Changes (In Priority Order)

### 1. Persist Planner Output

At the entry point of request handling:

- Call `ConversationPlannerAgent.plan(...)`
- Persist the returned plan immediately
- Generate and store a `plan_id`
- The plan must be append-only and immutable

Suggested model (or equivalent):

- PlanRecord
  - id (UUID, plan_id)
  - session_id
  - intent
  - plan_json
  - metadata
  - created_at
  - executed (boolean)

The planner MUST return:
- plan_id
- intent
- plan (ordered list of steps)
- metadata

---

### 2. Move Heuristics Into the Planner

Remove inline heuristics from:

- src/services/session_service.py

Examples include (but are not limited to):
- color/styling detection
- sequence diagram bypass logic
- ingest fallback paths

All heuristics must live in:
- ConversationPlannerAgent.plan(...)

If logic must run before planning, it must feed signals INTO the planner — not bypass it.

---

### 3. Planner-Only Execution Flow

Update `handle_message(...)` so that:

- It NEVER calls tools directly
- It ONLY:
  1) calls planner.plan(...)
  2) persists the plan
  3) iterates over plan steps
  4) executes each step via `mcp_registry.execute(...)`

Each step execution must include:
- plan_id in execution context
- step name
- arguments

Execution results must be collected and stored per plan step.

---

### 4. Normalize MCP Tool Outputs (Auditability)

All MCP tools — especially styling tools — must:

- Create a StylingAudit when applicable
- Return outputs in a consistent shape
- Always include `audit_id` when an audit is created

Example normalized tool output shape:
- success
- audit_id (if applicable)
- payload (svg / ir / metadata)

Add a small normalization layer in:
- src/mcp/tools.py

---

### 5. Link Audits to Plans

Enhance:
- src/services/styling_audit_service.py

So that:
- audits can be linked to plan_id
- audits can be retrieved by plan_id
- diagrams can expose their styling audit trail

StylingAudit records must reference plan_id where relevant.

---

### 6. Execution Logging Hooks

Add structured logging at:

- Before planner.plan(...)
- After planner.plan(...)
- Before mcp_registry.execute(...)
- After mcp_registry.execute(...)

All logs must include:
- session_id
- plan_id
- tool name (if applicable)
- audit_id (if returned)
- duration

These logs are for debugging and observability, not UI.

---

### 7. API and UI Integration

Backend:
- Include plan_id in chat API responses
- Add an endpoint to fetch plan + execution history by plan_id

Frontend (ui/src/App.jsx):
- If plan_id is present:
  - fetch plan and execution history
  - render collapsible plan JSON
  - render execution steps
  - link styling audits
  - show diffs where possible

UI should treat plan + audits as first-class artifacts.

---

## Files Expected to Change

Backend:
- src/db_models.py
- src/services/session_service.py
- src/agents/conversation_planner_agent.py
- src/mcp/tools.py
- src/mcp/registry.py
- src/services/styling_audit_service.py
- src/server.py (API responses)

Frontend:
- ui/src/App.jsx

Tests:
- planner unit tests
- planner-only execution integration tests
- styling audit linkage tests

---

## Tests to Add (Mandatory)

1) Unit test:
- A message that previously triggered heuristic styling
- Must now produce a planner step for styling

2) Integration test:
- handle_message persists PlanRecord
- MCP execution creates StylingAudit
- audit references plan_id
- API returns linked audit

---

## Acceptance Criteria (Strict)

- Every chat request produces a persisted plan_id
- No tool is executed outside mcp_registry.execute(...)
- No heuristic bypass remains in session_service
- Styling tools always return audit_id
- UI can fetch and display plan + execution + audits
- All tests pass

---

## Commit Strategy (Follow This Order)

1) DB model + migration
2) Planner return shape + unit tests
3) session_service refactor (planner-only flow)
4) MCP tool normalization + audit linkage
5) Logging hooks
6) UI integration
7) Integration tests

---

## Final Principle (Non-Negotiable)

Planning is explicit.  
Execution is mediated.  
Audits are mandatory.

Implement accordingly.