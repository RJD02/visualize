Goal
Enable MCP-based discovery and remote execution for the application's Styling Agent so clients can discover tools and invoke styling operations remotely.

Context
Repo root: /home/goku/dev/visualization
Key modules: src/mcp/*, src/services/styling_audit_service.py, src/agents/*, src/aesthetics/*, src/server.py, src/db_models.py, src/schemas.py

Deliverables
1) Register styling tools (pre-svg/post-svg) in src/mcp/tools.py with full metadata (id, name, description, input schema, output schema, mode).
2) Ensure MCP registry exposes discovery metadata and an execute dispatch: /mcp/discover and /mcp/execute (HTTP adapter acceptable for POC).
3) Instrument Styling Agent to create immutable StylingAudit records via src/services/styling_audit_service.py for every styling action (save intent, plan, steps, reasoning, before/after artifacts).
4) Add GET audit endpoints:
   - GET /api/diagrams/{diagramId}/styling/audit
   - GET /api/diagrams/{diagramId}/styling/audit/{auditId}
5) Add minimal HTTP client in src/mcp/client/ to call /mcp/discover and /mcp/execute.
6) Tests: unit + integration for discovery, execute, and audits (cover specs_v28 tests 1–5).

Concrete tasks for the agent (ordered)
- Add DB model + Pydantic schema for StylingAudit (append-only).
- Implement src/services/styling_audit_service.py create/get/list.
- Update styling planner/executor (suggest: src/aesthetics/aesthetic_intelligence.py or agents/visual_agent.py) to:
  - call extractStylingIntent(), generateStylingPlan(), record executionSteps/reasoning,
  - call styling_audit_service.create(...) with appropriate before/after fields (rendererInput vs svg depending on mode).
- Extend src/mcp/tools.py to register:
  - "styling.apply_pre_svg"
  - "styling.apply_post_svg"
  with metadata and an execute wrapper that returns auditId.
- Add src/mcp/transport_http.py (or extend src/server.py) to serve:
  - GET /mcp/discover -> list registered tools with metadata
  - POST /mcp/execute -> {tool_id, args} -> invoke MCPRegistry and return result
- Implement src/mcp/client/http_client.py to call the above.
- Wire startup: src/server.py should call register_mcp_tools(...) and mount transport endpoints.
- Write tests that:
  - call /mcp/discover and assert styling tools present
  - call /mcp/execute for pre/post modes and assert audit record created with before/after artifacts
  - verify append-only history and agent reasoning text

Example tool metadata (register each tool):
{
  "id": "styling.apply_pre_svg",
  "name": "Apply Pre-SVG Styling",
  "description": "Modify renderer input before SVG generation; returns rendererInputAfter and auditId",
  "inputs": {"diagramId":"string","userPrompt":"string","rendererInput":"string"},
  "outputs": {"rendererInputAfter":"string","auditId":"uuid"},
  "mode":"pre-svg",
  "version":"v1"
}

Acceptance criteria
- /mcp/discover lists styling tools with rich metadata.
- /mcp/execute can invoke registered styling tools remotely and returns auditId.
- Every styling request creates an immutable StylingAudit (ISO8601 timestamps).
- GET audit endpoints return full audit record (intent, plan, steps, reasoning, before/after).
- Tests from specs_v28 pass.

Constraints
- Do not mix pre-svg and post-svg artifacts in same audit entry.
- Keep audit records append-only.
- For POC use HTTP; design transport adapter to be replaceable later.

Stop conditions
Return a PR/branch with small commits, updated tests, and a README showing how to:
1) call /mcp/discover
2) call /mcp/execute
3) fetch audits via API