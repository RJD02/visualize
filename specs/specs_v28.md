# Codex Prompt — Add Styling Auditability (Planning + Actions Visible in UI)

You are a senior engineer tasked with adding **auditability to the styling subsystem**
of an AI-powered diagramming application.

---

## Context

- Users generate diagrams from text, documents, GitHub repos, or previous SVGs.
- Mermaid and PlantUML are integrated.
- Styling can be applied:
  - **Pre-SVG** (during diagram generation)
  - **Post-SVG** (direct SVG transformation)
- A dedicated **Styling Agent** exists (or will exist) via MCP / Google ADK.
- Styling can be requested through the **chat window**.
- Currently, the system applies styles but does NOT expose:
  - how intent was extracted
  - how plans were formed
  - what steps were taken

This reduces trust, debuggability, and iteration speed.

---

## Goal

Add a **full auditability layer** so that:

1. The system records how styling decisions were made
2. The agent’s planning and execution steps are logged
3. Users can inspect these steps in the UI
4. Each styling action is traceable, explainable, and reproducible

---

## Core Design Principles (Non-Negotiable)

1. Styling decisions must be **explainable**
2. Styling execution must be **inspectable**
3. Styling history must be **immutable**
4. Audit data must be **human-readable**
5. Audit data must be **machine-verifiable**

---

## Architecture Extension

Chat Request
   ↓
Styling Intent Extraction
   ↓
Styling Agent (Planner)
   ↓
Styling Plan
   ↓
Styling Executor (pre-SVG or post-SVG)
   ↓
Styled SVG
   ↓
Audit Log + UI Visualization

---

## Tasks

### 1. Add Styling Audit Data Model

Create a persistent audit model:

```json
StylingAudit {
  id: UUID,
  timestamp: ISO8601,
  diagramId: String,
  userPrompt: String,
  extractedIntent: JSON,
  stylingPlan: JSON,
  executionSteps: [String],
  rendererInputBefore: String | null,
  rendererInputAfter: String | null,
  svgBefore: String | null,
  svgAfter: String | null,
  agentReasoning: String
}
```

Definitions:
	•	extractedIntent: structured interpretation of user request
	•	stylingPlan: semantic → visual mapping
	•	executionSteps: ordered list of actions taken
	•	agentReasoning: plain-English explanation

Audit entries must be append-only.

2. Instrument the Styling Agent

Modify the Styling Agent so that it explicitly logs:
	1.	Intent extraction
	2.	Plan generation
	3.	Execution steps
	4.	Reasoning

Pseudo-flow:
intent = extractStylingIntent(chatInput)
plan = generateStylingPlan(intent, diagramContext)

steps = []
reasoning = []

for each planStep:
  steps.append(describe(planStep))
  reasoning.append(explain(planStep))

saveAudit({
  userPrompt,
  extractedIntent: intent,
  stylingPlan: plan,
  executionSteps: steps,
  agentReasoning: reasoning.join("\n")
})

3. Support Both Pre-SVG and Post-SVG Auditing

Pre-SVG Styling
	•	Save:
	•	renderer input before styling
	•	renderer input after styling

Post-SVG Styling
	•	Save:
	•	SVG before styling
	•	SVG after styling

Do NOT mix these two modes.

⸻

4. UI Integration — “View Styling Plan”

Add a UI control near each diagram:
[ View Diagram ] [ View Styling Plan ] [ Animate ] [ Export ]

When “View Styling Plan” is clicked, display:
	•	User prompt
	•	Extracted styling intent (JSON)
	•	Styling plan (JSON)
	•	Agent reasoning (text)
	•	Execution steps (ordered list)
	•	Diff view:
	•	SVG before → after
	•	or renderer input before → after

UI requirements:
	•	Collapsible JSON
	•	Clear timestamps
	•	Readable explanations
	•	Highlighted diffs

⸻

5. Audit API Endpoints

Expose APIs:
GET /api/diagrams/{diagramId}/styling/audit
GET /api/diagrams/{diagramId}/styling/audit/{auditId}

Responses must include:
	•	metadata
	•	reasoning
	•	execution steps
	•	before/after artifacts

⸻

Test Cases (Automated)

Test 1 — Simple Color Styling

User:
“Use orange and yellow blocks”

Expect:
	•	Styling audit created
	•	Intent contains color semantics
	•	Plan shows block-level styling
	•	Execution steps logged

Test 2 — Post-SVG Text Styling

User:
“Make all labels bold”

Expect:
	•	SVG before/after stored
	•	<text> styling changes logged
	•	Agent reasoning explains decision


Test 3 — Incremental Styling

User:
“Highlight database in red”

Expect:
	•	Only DB element modified
	•	Audit explains selection logic
	•	Other elements unchanged

Test 4 — Styling + Animation

User:
“Animate and highlight API path”

Expect:
	•	Separate styling vs animation steps
	•	Styling audit remains independent
	•	Clear execution order

⸻

Test 5 — Styling History

User applies multiple styling updates

Expect:
	•	Multiple audit entries
	•	UI shows full history
	•	Older audits remain unchanged

Success Criteria (POC Pass)

All must be true:
	•	Every styling request generates an audit record
	•	Styling plans are visible in the UI
	•	Agent reasoning is understandable to humans
	•	Before/after diffs are inspectable
	•	Styling history is preserved
	•	Tests pass before manual verification

Philosophy (Do Not Violate)

This system must not be a black box.

Users should always be able to answer:
	•	What was changed?
	•	Why was it changed?
	•	How was the decision made?

If styling cannot be explained, it is a bug.