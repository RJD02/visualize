# specs_v32 — LLM-generated UML prompt for Copilot agent

Date: 2026-02-10

## Purpose

Add support for accepting LLM-generated UML diagrams (PlantUML and Mermaid) produced by the Conversation Planner / LLM, validate and sanitize them, feed into existing renderers, and ensure all styling runs are auditable and linked to planner `plan_id` and `audit_id`.

This file contains a single Copilot-agent prompt and an implementation checklist for engineers to follow.

## Background

Currently `src/tools/plantuml_renderer.py` produces PlantUML from an `ArchitecturePlan` and explicitly forbids aesthetic/style directives. We want to allow the planner (or constrained LLM step) to optionally return a raw UML string (PlantUML or Mermaid). The system must validate and sanitize that string, persist an audit (`StylingAudit`), and render it using the corresponding renderer.

Goals:
- Accept `llm_diagram` (string) in planner/MCP steps when the planner chooses LLM-generated UML.
- Support both `plantuml` and `mermaid` formats.
- Validate and sanitize diagrams server-side to block unsafe directives (file includes, external URLs, server-side commands).
- Persist plan and audit linkage (`plan_id` ↔ `audit_id`).
- Maintain backward compatibility: if `llm_diagram` absent, fallback to programmatic generation.

## Implementation Checklist (high level)

1. Add validator: create `src/tools/diagram_validator.py` which exposes `validate_and_sanitize(diagram_text, format)`.
2. Update MCP signatures: ensure styling tools accept `llm_diagram` and `format` and always return `{ audit_id, rendered_svg, warnings? }`.
3. Modify `src/tools/plantuml_renderer.py` to accept an optional `llm_plantuml` string; when present, validate, sanitize and render it; otherwise keep existing generation.
4. Add or update Mermaid renderer (e.g., `src/tools/mermaid_renderer.py`) with the same optional-LLM behavior.
5. Ensure `src/services/styling_audit_service.py` is called for every LLM styling request and returns `audit_id` recorded in DB with `plan_id`, original `llm_diagram`, `format`, and sanitized output.
6. Add unit/integration tests: sanitization rules, audit creation, CLI/HTTP flows, and UI visibility.
7. Update documentation and add migration notes if DB schema changes.

## Security & Sanitization Rules

- Reject or strip PlantUML directives that reference external files or URLs (e.g., `!include`, `!import`, `skinparam backgroundImage`, `url(...)`).
- Block `!pragma` or any server-side exec-like tokens. Allow only a whitelist of PlantUML constructs (component, package, actor, note, relationships, skinparam limited list) when in sanitized mode.
- For Mermaid, block `%%{init:...}%%` blocks that allow remote resources or JS extensions, and disallow HTML injection in labels.
- Log and persist any rejected tokens or warnings in the `StylingAudit` record.

## Copilot-Agent Prompt (for implementation)

You are GitHub Copilot (developer-mode). Implement the following changes in the repository to accept LLM-generated UML for PlantUML and Mermaid, validate it, and ensure audits are created and linked to planner output.

Requirements (explicit):

- Files to change/implement:
  - `src/tools/diagram_validator.py` (new)
  - `src/tools/plantuml_renderer.py` (update)
  - `src/tools/mermaid_renderer.py` (new or update existing mermaid tooling)
  - `src/mcp/tools.py` (ensure MCP tool signatures accept `llm_diagram`, `format`, and return `audit_id`)
  - `src/services/styling_audit_service.py` (ensure `record_styling_audit` accepts `llm_diagram`, `sanitized_diagram`, and persists `format`)
  - `src/services/session_service.py` (when calling planner and executing plan steps, persist `plan_id` before executing LLM diagrams and forward `plan_id` to tool execution)

- Behavior:
  - If a plan step contains `llm_diagram` and `format` is `plantuml` or `mermaid`, call `validate_and_sanitize` and then render using the corresponding renderer.
  - The validator returns `{ sanitized_text, warnings, blocked_tokens }`.
  - The styling tool must call `record_styling_audit(plan_id, input_text, sanitized_text, format, intent, warnings)` and return `{ audit_id, rendered_svg, warnings }` to the caller.
  - The renderers must *never* execute remote includes or shell out to untrusted processes.
  - On validation failure (unsafe tokens), return a structured error object and do not render; surface to the UI.

- Tests to add:
  - `tests/test_diagram_validator.py`: cover allowed constructs, blocked `!include` and `url(...)`, mermaid `%%{init}` blocking.
  - `tests/test_plantuml_llm_flow.py`: end-to-end test: planner produces `llm_diagram`, server records `StylingAudit`, renderer returns SVG, and response includes `audit_id`.
  - `tests/test_mermaid_llm_flow.py`: equivalent for mermaid.

- Examples (for test fixtures):
  - PlantUML allowed example:

    @startuml
    component "Backend" as B
    component "DB" as D
    B --> D : reads
    @enduml

  - PlantUML disallowed example (test should assert rejection):

    !include https://example.com/malicious.puml
    @startuml
    A -> B
    @enduml

  - Mermaid allowed example:

    graph LR
      A[Client] --> B[Server]

  - Mermaid disallowed example:

    %%{init: {"themeVariables": {"dark": true}}}%%
    graph LR
      A --> B

Implementation notes and hints:

- Keep API/contract backward compatible: existing non-LLM flow must remain unchanged.
- Reuse existing rendering code paths where possible; add a small wrapper function `render_from_llm(text, format)` that validates and passes into the renderer.
- Persist planner output early in `session_service` (a new `PlanRecord`) with generated `plan_id`, then pass `plan_id` down into the MCP execute calls so audits can link back.
- Ensure every successful styling run results in a `StylingAudit` row with `plan_id` and returned `audit_id`.
- Add clear logging for sanitization warnings and rejection reasons.

Acceptance Criteria

- Pull request changes implement the files above and all tests pass (`pytest`).
- The server returns `{ audit_id }` for successful LLM-styling operations.
- UI endpoints that list audits continue to work and show the new LLM-origin audits.

## Backward compatibility & rollout

- Feature guarded: new behavior only triggers when a plan step contains `llm_diagram` + `format`.
- Do not change existing database schemas unless necessary; if schema changes are required, include a migration file and note in this spec.

## Migration notes (if adding fields)

- If adding fields to `StylingAudit` (e.g., `original_llm_text`, `format`, `sanitized_text`), add a small Alembic-style migration or include a note for manual migration.

---

End of spec v32.
