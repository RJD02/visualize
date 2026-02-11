# specs_v33 — Planner-led renderer selection & orchestrator execution

Date: 2026-02-10

## Purpose

Make the Conversation Planner the authoritative decision-maker for how to render diagram semantics returned from the IR. The planner should choose the rendering service (e.g., programmatic generator, LLM-produced PlantUML, Mermaid renderer, or external renderer service) and produce a deterministic, auditable plan that the orchestrator executes.

This spec contains a concise Copilot-agent prompt and a prioritized list of code locations to change.

## Short Copilot-Agent Prompt

Make the `ConversationPlannerAgent` the single source of truth for rendering decisions. Implement these changes so the planner selects `rendering_service` per `plan_step` (values: `programmatic`, `llm_plantuml`, `llm_mermaid`, `external_service`) and emits `llm_diagram` only when constrained by schema. Persist `plan_id` before execution, pass `plan_id` to MCP tool calls, validate and sanitize any LLM output server-side, record a `StylingAudit` for every styling operation, and ensure the orchestrator executes the plan exactly as written. Limit hallucination by requiring LLM outputs to conform to a small JSON schema and by validating tokens before rendering. Update tests and UI to surface plan/audit linkage.

## Where to Change (high priority)

- `src/services/session_service.py`:
  - Persist `PlanRecord` immediately after `ConversationPlannerAgent.plan(...)` returns and before execution.
  - Pass `plan_id` into each `mcp_registry.execute(...)` call.
  - Replace ad-hoc heuristics with planner-driven `plan.steps` handling.

- `src/services/planner_agent.py` or `src/services/conversation_planner_agent.py` (where agent lives):
  - Add `rendering_service` and `format` fields to plan step outputs.
  - When opting for LLM-generated diagrams, require the planner to output `llm_diagram` as structured JSON:
    {"format":"plantuml|mermaid","diagram":"<text>","schema_version":1}
  - Ensure planner uses constrained prompt/JSON schema to avoid free-text UML.

- `src/mcp/tools.py`:
  - Update styling tool registrations to accept `plan_id`, `rendering_service`, `llm_diagram` and return `{ audit_id, file_path, warnings }`.

- `src/tools/diagram_validator.py` (new):
  - Implement `validate_and_sanitize(text, format)` returning `{ sanitized_text, warnings, blocked_tokens }`.
  - Enforce token whitelist/blacklist and strip `!include`, `!pragma`, external URLs, and Mermaid `%%{init}` blocks.

- `src/tools/plantuml_renderer.py` and `src/tools/mermaid_renderer.py`:
  - Add wrappers `render_from_llm(text, output_name, ...)` that call the validator first, persist sanitized text, then render using existing safe renderer paths.
  - Ensure no remote includes or shell escapes are executed.

- `src/services/styling_audit_service.py`:
  - Ensure `record_styling_audit(plan_id, origin, input_text, sanitized_text, format, warnings)` exists and returns `audit_id`.

- `src/db_models.py`:
  - Add `PlanRecord` model (append-only) with `id`, `plan_json`, `created_at`, `author`.
  - Extend `StylingAudit` to optionally store `original_llm_text`, `format`, `sanitized_text`.

- `src/server.py`:
  - Ensure `/mcp/execute` and other endpoints accept and forward `plan_id` and return `audit_id` when appropriate.

- `ui/src`:
  - Surface `plan_id` and `audit_id` linkage in diagram views and the "View Styling Plan" flow.

## Where to Change (medium priority)

- Tests: add unit & integration tests for planner-led rendering decisions and audit recording.
- Documentation: `README.md` and `specs/*` updates describing new contract and migration notes.

## Determinism & Hallucination Controls

- Use structured outputs: require planner LLM to emit `llm_diagram` inside a bounded JSON schema. Reject free-form UML unless the schema is strictly followed.
- Validate and sanitize server-side with `diagram_validator.py` before any render.
- Add `schema_version` and `constraints` fields to `plan_step` to make future validation explicit.

## Tests & Acceptance Criteria

- Planner writes `PlanRecord` to DB and returns `plan_id`.
- Orchestrator executes plan steps in order, passing `plan_id` to tools.
- For LLM-produced diagrams: server validates the JSON schema, sanitizes text, records `StylingAudit`, and returns `audit_id` and rendered file path.
- UI shows links from diagram → `plan_id` → `audit_id` and displays warnings when sanitization removed tokens.

## Suggested Implementation Sequence

1. Add `PlanRecord` model and migration.
2. Implement `diagram_validator.py` and tests.
3. Update planner agent to emit `rendering_service` and constrained `llm_diagram` JSON.
4. Persist `plan_id` in `session_service` and pass it into MCP executions.
5. Update MCP tools and renderers to accept `plan_id` and call `record_styling_audit`.
6. Add end-to-end tests and UI wiring.

## Short developer note for Copilot:

Prioritize minimal, well-scoped changes that make the planner the decision-maker and add robust validation. Keep backward compatibility: when `rendering_service` absent, fallback to existing programmatic generation.

---

End of spec v33.
