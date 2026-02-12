Integration v2 — Block-level editability + MCP tool

Goal

1. Block-level editability feedback loop: user can give feedback about a specific block/zone/text/whole-diagram; the agent updates the intermediate representation (IR) accordingly and re-generates the diagram. The IR must be enhanced (if needed) to represent blocks with unique IDs, bounding boxes, text, style and annotations.

2. Expose the agent as a reusable MCP tool: provide an explicit programmatic interface, manifest, payload schemas and lightweight adapter so another MCP can use the tool to generate diagrams and process feedback.

Scope & Acceptance Criteria

- The IR must include block-level metadata: `id`, `type`, `text`, `bbox`, `style`, `annotations`, `version`.
- UI must allow selecting a block and submitting feedback (change text, change style, reposition, hide/show, add annotation).
- Backend must accept feedback payloads, map to IR transforms, validate them, apply the transform, and re-run the diagram generator to produce a new diagram artifact (PUML/PlantUML, mermaid, etc.).
- A Cypress E2E test must simulate generating a diagram, selecting a block, submitting a feedback change (e.g., replace label text), and assert the regenerated diagram reflects the change.
- Unit tests should verify IR transform correctness.
- Provide an `MCP tool` wrapper exposing endpoints and a manifest that documents the tool API.

Files to create / modify (suggested)

- `src/ir.py` — canonical IR classes and JSON schema.
- `src/ir_transforms.py` — pure functions to apply edits to IR.
- `src/feedback_controller.py` — HTTP/IPC controller to accept feedback and trigger generation.
- `src/mcp_tool.py` — adapter exposing the tool to other MCPs (RPC/HTTP wrapper + manifest loader).
- `ui/diagram/DiagramViewer.*` — add block selection and data attributes: `data-block-id`.
- `ui/diagram/FeedbackModal.*` — UI for submitting feedback with type + payload.
- `tests/test_ir_transforms.py` — pytest unit tests.
- `cypress/integration/feedback_spec.cy.js` — E2E feedback loop tests.
- `specs/mcp_tool_manifest.json` — manifest describing endpoints and payloads.
- `specs/integration_v2.md` — this file (written).

IR: Suggested JSON Schema (example)

{
  "ir_version": "2.0",
  "diagram": {
    "id": "diagram_123",
    "type": "system_architecture",
    "blocks": [
      {
        "id": "block-1",
        "type": "container|component|actor|note",
        "text": "User Service",
        "bbox": {"x":100,"y":20,"w":200,"h":60},
        "style": {"color":"#123456","shape":"rounded"},
        "annotations": {"owner":"team-a"}
      }
    ],
    "relations": [{"from":"block-1","to":"block-2","label":"calls"}]
  }
}

Design notes

- Every rendered DOM element for a block should include `data-block-id="block-1"` so front-end can map user clicks to specific IR blocks.
- Keep `src/ir.py` and renderer input/output decoupled; add a small adapter if current generators accept different formats.
- IR transforms should be pure functions that take IR + edit -> new IR (and optionally a list of validation warnings).

Feedback payload

- POST JSON payload to `/api/feedback` (or MCP RPC equivalent):
  {
    "diagram_id": "diagram_123",
    "feedback_id": "fb-uuid",
    "block_id": "block-1",            // optional if feedback targets whole diagram
    "action": "edit_text|reposition|style|hide|annotate|add_block|remove_block",
    "payload": { ... },
    "author": "user@example.com",
    "timestamp": 167xxx
  }

Examples

- Change text:
  {"action":"edit_text","payload":{"text":"Auth Service"}}
- Reposition:
  {"action":"reposition","payload":{"bbox":{"x":150,"y":60}}}
- Style change:
  {"action":"style","payload":{"style":{"color":"#FF0000"}}}

Server: feedback processing pseudocode

1. Receive feedback JSON.
2. Load current IR for `diagram_id` from disk/db (e.g., `outputs/..._architecture_plan.json`).
3. Run `ir_transforms.apply(feedback, ir)` -> new_ir, patches
4. Validate `new_ir` (schema + domain checks).
5. Persist `new_ir` (version bump).
6. Call generator: `generator.render(new_ir)` -> artifacts (PUML, images).
7. Return status + artifact locations to caller.

MCP Tool: API & manifest

- Exposed functions (HTTP/RPC):
  - `generate(diagram_spec)` -> `{diagram_id, artifacts, ir}`
  - `feedback(feedback_payload)` -> `{status, ir, artifacts}`
  - `get_ir(diagram_id)` -> `ir`
  - `list_artifacts(diagram_id)` -> `[{path, type}]`

Manifest example (`specs/mcp_tool_manifest.json`):

{
  "name": "visualization-diagram-tool",
  "version": "0.2",
  "endpoints": {
    "generate": {"method":"POST","path":"/mcp/tool/generate","payloadSchema":"specs/schemas/generate.json"},
    "feedback": {"method":"POST","path":"/mcp/tool/feedback","payloadSchema":"specs/schemas/feedback.json"},
    "get_ir": {"method":"GET","path":"/mcp/tool/ir/{diagram_id}"}
  }
}

MCP adapter: contract

- Provide a small `src/mcp_tool.py` with functions:

def generate(diagram_spec: dict) -> dict:
    """Create diagram from spec. Returns {diagram_id, ir, artifacts}."""

def apply_feedback(feedback_payload: dict) -> dict:
    """Apply feedback, re-generate diagram. Returns {status, ir, artifacts}."""

def get_ir(diagram_id: str) -> dict:
    """Return the current IR for diagram."""

- The wrapper should be lightweight and return JSON-serializable types.

Testing

Unit tests (pytest): `tests/test_ir_transforms.py`

- Test 1: edit_text updates the correct block text
- Test 2: reposition changes `bbox` and keeps other fields
- Test 3: invalid block_id -> error or validation warning
- Test 4: add_block appends a new block with generated id and valid bbox

Example pytest test:

import copy
from src.ir_transforms import apply_feedback

def sample_ir():
    return {
        "ir_version":"2.0",
        "diagram":{"id":"d1","blocks":[{"id":"b1","text":"Old","bbox":{"x":0,"y":0,"w":100,"h":40}}]}
    }

def test_edit_text():
    ir = sample_ir()
    fb = {"diagram_id":"d1","block_id":"b1","action":"edit_text","payload":{"text":"New"}}
    new_ir, patches = apply_feedback(fb, ir)
    assert any(b for b in new_ir["diagram"]["blocks"] if b["id"]=="b1" and b["text"]=="New")

Cypress E2E tests: `cypress/integration/feedback_spec.cy.js`

- Flow:
  1. Visit the local app route that renders a test diagram (e.g., `/demo?fixture=sample1`).
  2. Wait for diagram to render.
  3. Click the block element: `cy.get('[data-block-id="b1"]').click()`.
  4. Open feedback modal: click button or ensure modal opens.
  5. Change the label text to `Auth Service Updated` and submit.
  6. Wait for regeneration to finish (poll backend or check UI spinner).
  7. Assert: new DOM contains updated text: `cy.contains('Auth Service Updated')` and/or check updated artifact fetched from `/api/ir/{diagram_id}`.

Example test code:

describe('Diagram feedback loop', () => {
  it('applies edit_text feedback and re-renders diagram', () => {
    cy.visit('/demo?fixture=sample1')
    cy.get('[data-block-id="b1"]', {timeout:10000}).should('be.visible').click()
    // open modal
    cy.get('#open-feedback').click()
    cy.get('#feedback-action').select('edit_text')
    cy.get('#feedback-text').clear().type('Auth Service Updated')
    cy.get('#submit-feedback').click()
    // wait for regeneration; adjust the wait strategy to your stack
    cy.intercept('POST','/api/feedback').as('postFeedback')
    cy.wait('@postFeedback')
    cy.contains('Auth Service Updated', {timeout:15000}).should('exist')
  })
})

How to run tests

- Run pytest unit tests:

```bash
python -m pytest tests/test_ir_transforms.py -q
```

- Run Cypress (local):

```bash
npx cypress open
# or headless
npx cypress run --spec cypress/integration/feedback_spec.cy.js
```

Implementation guidance and code examples

1. `src/ir.py` — canonical IR objects
   - Provide `IR` class with `to_json()` and `from_json()` helpers.
   - Provide `validate_ir(ir_json)` checks. Use `jsonschema` if available.

2. `src/ir_transforms.py`
   - Implement `apply_feedback(feedback, ir_json)` returning `(new_ir, patches)`.
   - Patches should be a simple list of transformations applied for audit.

Example skeleton:

def apply_feedback(feedback, ir):
    diagram = ir['diagram']
    action = feedback['action']
    block_id = feedback.get('block_id')
    if block_id:
        block = find_block(diagram, block_id)
        if not block: raise ValueError('block not found')
    if action == 'edit_text':
        block['text'] = feedback['payload']['text']
    elif action == 'reposition':
        block['bbox'].update(feedback['payload']['bbox'])
    # ... more actions
    ir['ir_version'] = bump_version(ir['ir_version'])
    return ir, patches

3. `src/feedback_controller.py` — minimal example

from flask import Flask, request, jsonify
from src.ir_transforms import apply_feedback
from src.generator import render_from_ir

app = Flask(__name__)

@app.route('/api/feedback', methods=['POST'])
def feedback():
    fb = request.json
    ir = load_ir(fb['diagram_id'])
    new_ir, patches = apply_feedback(fb, ir)
    save_ir(fb['diagram_id'], new_ir)
    artifacts = render_from_ir(new_ir)
    return jsonify({"status":"ok","ir":new_ir,"artifacts":artifacts})

4. `src/mcp_tool.py` — adapter

def mcp_generate(diagram_spec):
    ir = spec_to_ir(diagram_spec)
    artifacts = render_from_ir(ir)
    return {"diagram_id":ir['diagram']['id'],"ir":ir,"artifacts":artifacts}

def mcp_feedback(feedback_payload):
    return feedback_controller.apply_feedback(feedback_payload)

Test cases (detailed)

1) Unit tests for `apply_feedback` (python/pytest):
- assert that when `action=edit_text` with valid `block_id` -> text changed.
- assert that when `block_id` missing for `edit_text` -> error or apply to diagram root.
- assert for `add_block` that new block appears and `id` generated.

2) Cypress E2E tests simulate a real user interaction as shown earlier.

3) Integration test (optional): an automated harness that posts feedback JSON directly to `/api/feedback`, downloads the resulting artifact (PUML) and asserts the PUML contains the new label.

Example artifact assertion (node or python):
- POST feedback -> GET artifact path -> assert `Auth Service Updated` in `.puml` or generated image alt text.

Runbook & developer notes

- Preserve backward compatibility: if older IRs exist, write a conversion helper `upgrade_ir_v1_to_v2()`.
- Be conservative about automatic re-layouts; small text edits should not always trigger large repositioning. For more complex layout changes, mark the change with `needs_layout:true` in IR.
- Add logging/audit for feedback events and patches applied.

CI

- Add a GitHub Actions workflow or similar that runs `pytest` and `npx cypress run` on PRs.
- Cache node modules and python venv where possible.

Deliverable for Codex agent (prompt)

Below is an explicit prompt you can feed to your Codex agent. The agent should:
- Modify code in the repository to implement the features above.
- Add the tests and specs files referenced.
- Keep changes minimal and maintain style consistency.

--- BEGIN CODEX PROMPT ---
You are a developer working on the `visualization` repo. Implement block-level editability and expose the agent as an MCP tool, following the spec in `specs/integration_v2.md`.

Work items (do these in order and commit each change):
1. Add IR v2 schema and helpers in `src/ir.py`. Provide `to_json/from_json/validate_ir` functions and a migration helper from v1 to v2 if needed.
2. Add `src/ir_transforms.py` implementing `apply_feedback(feedback: dict, ir: dict) -> (new_ir, patches)` and unit tests in `tests/test_ir_transforms.py` covering edit_text, reposition, add_block and invalid block.
3. Add a `src/feedback_controller.py` that exposes an HTTP endpoint `POST /api/feedback`. It should:
   - validate payload
   - load and apply transforms
   - persist new IR
   - invoke the existing generator used by the project and return artifact locations
4. Update UI (under `ui/diagram`) to add `data-block-id` attributes on rendered blocks. Add a `FeedbackModal` component and a small integration that sends JSON to `/api/feedback`.
5. Create a Cypress E2E test `cypress/integration/feedback_spec.cy.js` that runs the user flow: open diagram, select block, open modal, edit text, submit, and assert re-rendered text exists.
6. Add `src/mcp_tool.py` and `specs/mcp_tool_manifest.json` describing `generate`, `feedback`, `get_ir` endpoints and expected payloads. Keep the adapter minimal: functions return JSON serializable dicts.
7. Add CI workflow steps to run `pytest` and `npx cypress run`.
8. Add clear README notes for how to run tests locally.

Testing expectations:
- All pytest tests pass.
- Cypress test passes in headless mode.
- Manual test: POST a `feedback` JSON to `/api/feedback` and confirm artifacts update.

When you produce edits, ensure every new file is added under the paths referenced, and add small unit tests demonstrating correctness. Return a summary list of changed files, tests added and how to run them.

--- END CODEX PROMPT ---

Notes

- Place this file as `specs/integration_v2.md` (already created) and deliver a PR that makes the above changes.
- If the code generator requires a specific IR flavor, add a small adapter `src/ir_adapter.py` to convert our IR -> generator input.



Consider below specifications as well in case something was missed from above specifications:

# Codex Prompt — Add Block-Level Feedback Editing + MCP Tool Exposure

You are a senior systems engineer extending the diagram generation platform.

The POC is near completion. Two major features must now be implemented:

1) Block-level editability via user feedback (IR mutation + regeneration)
2) Expose this entire agent as a reusable MCP tool for other agents

The solution must be deterministic, auditable, testable via Cypress, and loop until passing.

---

# PART 1 — Block-Level Feedback Editing

## Goal

Allow the user to give feedback on a generated diagram such as:

- “Rename Compute Services to Compute Layer”
- “Move Data Lakehouse to external zone”
- “Change color of Data Teams to blue”
- “Remove Spark”
- “Make this diagram conceptual instead of operational”
- “Reduce edge density”
- “Highlight this node”

The system must:

1) Interpret feedback
2) Identify affected IR nodes/edges/zones/globalIntent
3) Mutate IR deterministically
4) Re-render diagram
5) Store diff + audit
6) Update UI

---

## Required Architectural Changes

### 1. Add IR Versioning

Each diagram must have:

```json
{
  "diagram_id": "...",
  "ir_version": 1,
  "parent_version": null,
  "ir": { ... }
}
```

On feedback:
	•	Create new version
	•	Store previous version
	•	Maintain immutable history

⸻

2. Add Feedback Interpreter Agent

Create a new agent:

ir_feedback_agent

Input:
	•	Previous IR
	•	User feedback text

Output:
	•	Structured IR mutation plan

Example:

Input feedback:
“Rename Compute Services to Compute Layer”

Mutation Plan:
```json
{
  "operation": "update_node_label",
  "node_id": "compute_services",
  "new_label": "Compute Layer"
}
```
Supported mutation types:
	•	update_node_label
	•	update_node_style
	•	update_edge_label
	•	delete_node
	•	delete_edge
	•	move_zone
	•	update_global_intent
	•	convert_diagram_type

⸻

3. IR Mutation Engine

Create deterministic IR patching logic.

Rules:
	•	Never re-generate IR from scratch.
	•	Only mutate specified fields.
	•	If node not found → return structured error.
	•	Log before/after diff.

⸻

4. Regeneration Pipeline

After IR mutation:

IR → Renderer → SVG → Styling Agent → Animation Agent → UI

Do not bypass styling or animation layer.

⸻

5. Audit Trail

Every feedback must produce:
```json
{
  "feedback": "...",
  "mutation_plan": {...},
  "ir_before": {...},
  "ir_after": {...},
  "diff_summary": "...",
  "confidence": 0.x
}
```

PART 2 — Expose as MCP Tool

The entire diagram engine must now be exposed as an MCP tool.

Tool name:
diagram_architect_agent

Capabilities:
	1.	generate_diagram
	2.	update_diagram
	3.	get_ir
	4.	get_ir_history
	5.	export_svg
	6.	export_gif

Example MCP interface:
```json
{
  "name": "diagram_architect_agent",
  "input_schema": {
    "action": "generate | update | inspect",
    "payload": {...}
  }
}
```

Ensure:
	•	Stateless invocation possible
	•	IR stored per diagram_id
	•	Deterministic outputs

PART 3 — Cypress Feedback Loop Tests

Create Cypress test suite:

diagram-feedback.cy.ts

Test 1 — Rename Node
	1.	Generate initial diagram
	2.	Send feedback:
“Rename Compute Services to Compute Layer”
	3.	Wait for regeneration
	4.	Assert SVG contains “Compute Layer”
	5.	Assert old label not present
	6.	Assert IR version incremented

⸻

Test 2 — Delete Node

Feedback:
“Remove Spark from the diagram”

Expect:
	•	Spark node removed
	•	No edges referencing spark
	•	IR mutation plan logged

⸻

Test 3 — Move Zone

Feedback:
“Move Data Lakehouse to external_services zone”

Expect:
	•	Node zone updated
	•	Diagram reflects new grouping
	•	IR diff shows zone change

⸻

Test 4 — Style Update

Feedback:
“Make Data Teams blue”

Expect:
	•	SVG style updated
	•	Node fill matches blue
	•	Mutation plan logged

⸻

Test 5 — Conceptual Conversion

Feedback:
“Convert this to conceptual diagram”

Expect:
	•	rel_type changes
	•	remove async/sync
	•	remove fabricated containers
	•	globalIntent updated

⸻

Test 6 — Feedback Loop Stability
	1.	Apply multiple feedback edits
	2.	Ensure:
	•	No orphaned edges
	•	No duplicate nodes
	•	Version chain intact
	•	No hallucinated components introduced

⸻

PART 4 — Determinism Rules
	1.	Feedback must mutate only specified fields.
	2.	No re-extraction from original text unless explicitly requested.
	3.	No hallucinated new nodes unless feedback explicitly requests creation.
	4.	Confidence must drop if mutation is ambiguous.
	5.	Cypress must fail if mutation not applied correctly.

⸻

SUCCESS CRITERIA

All must be true:
	•	User feedback updates diagram without full regeneration.
	•	IR versions stored and retrievable.
	•	Mutation plan is logged and viewable.
	•	Cypress tests pass.
	•	MCP interface works independently.
	•	No hallucinated structure introduced during feedback mutation.

⸻

PHILOSOPHY

This system must evolve from:

“Generate diagram from text”

to

“Maintain a living architectural model that can be edited, versioned, and reused by other agents.”

If feedback causes full re-generation instead of mutation, this is a failure.
If mutation cannot be audited, this is a failure.
If Cypress cannot detect the change, this is a failure.

Implement this fully and verify via Cypress before marking complete.