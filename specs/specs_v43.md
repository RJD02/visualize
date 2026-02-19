
⸻

You are a senior system architect.

Upgrade the diagram generation engine so that relationship extraction is first-class and deterministic.

Current problem:
The system extracts nodes correctly but fails to extract and render relationships defined in prompts.
Component diagrams are rendered without edges, even when instructions explicitly describe connections.

We must fix this.

Do not patch rendering.
Fix IR extraction and relationship modeling.

Implement the following.

⸻

PART 1 — Upgrade IR Schema

Extend IR to support structured relationships.

Add edge model:

{
“edge_id”: string,
“from”: string,
“to”: string,
“relation_type”: string,
“direction”: “unidirectional | bidirectional”,
“category”: “data_flow | user_traffic | replication | auth | secret_distribution | monitoring | control | metadata | network”,
“mode”: “sync | async | broadcast | conditional”,
“label”: string,
“confidence”: number
}

Edges are mandatory for any described connection.

If no explicit connections are found, attempt semantic inference.

⸻

PART 2 — Relationship Extraction Engine

Add deterministic relationship parsing before LLM fallback.

Detect verbs and phrases:

Map verbs to relation types:

connect → user_traffic or control
replicate / mirror → replication
supplies / injects / provides secrets → secret_distribution
writes / produces → data_flow
reads / queries → data_flow
authenticates / SSO → auth
monitors / collects metrics → monitoring
feeds → data_flow
publishes / consumes → data_flow
failover / promote → control

Use rule-based extraction first.

Example:
“Connect Users → Load Balancer”
Add edge from Users to Load Balancer (user_traffic).

“Vault supplies secrets to all runtime services”
Expand runtime services group and add edges:
Vault → each service (secret_distribution, broadcast mode).

“Observability connects to all components”
Add monitoring edges to every component node.

Multi-target relationships must expand deterministically.

⸻

PART 3 — Mandatory Edge Rendering

Modify diagram renderer so:

If IR contains edges:
	•	Render them.
	•	Apply style based on category.
	•	Do not skip rendering even if grouping exists.

Add style mapping table:

user_traffic → solid arrow
data_flow → solid arrow
replication → dashed arrow
secret_distribution → dotted arrow
monitoring → thin dashed arrow
auth → bold arrow

⸻

PART 4 — Enforce Relationship Presence Validation

If prompt contains relational verbs and IR produces zero edges:

Raise warning:
“Prompt contained relationship instructions but no edges were extracted.”

This prevents dry diagrams.

⸻

PART 5 — Component Diagram Semantics

Even for component diagrams:

If prompt describes flows,
edges must be rendered.

Component diagram must not default to node-only rendering.

⸻

PART 6 — Test Cases

Add automated tests:

Test 1:
Input:
“Connect A to B”
Expect:
1 edge A → B

Test 2:
Input:
“X replicates to Y”
Expect:
1 replication edge

Test 3:
Input:
“Vault supplies secrets to all services”
Expect:
N edges from Vault to each service

Test 4:
Input:
“Observability connects to all components”
Expect:
Edges to every node

Test 5:
Full infra prompt (the one provided earlier)
Expect:
	•	At least 10+ edges
	•	Replication edges present
	•	Auth flow present
	•	Data pipeline edges present

If less than threshold, test fails.

⸻

PART 7 — Improve Confidence Scoring

Each edge must include confidence.
If inferred (not explicit), lower confidence.

⸻

PART 8 — Do NOT Break Existing Features

Ensure:
	•	Styling agent still works.
	•	Animation layer can animate edges.
	•	Architecture grading agent uses edges.
	•	IR versioning remains intact.

⸻

PART 9 — Design Principle

Nodes describe structure.
Edges describe behavior.

Diagrams must show both.

Never render structure without flow if flow exists in prompt.

⸻

PART 10 — Final Goal

After this upgrade:
	•	Component diagrams must contain meaningful connections.
	•	Infrastructure diagrams must show traffic flow, replication, and control flow.
	•	The system must never output a dry node-only diagram when relational instructions are present.

Implement incrementally.
Add tests before modifying renderer.
Validate IR before render.

⸻

This prompt forces Codex to:
	•	Fix the real layer (IR)
	•	Add deterministic relationship extraction
	•	Enforce rendering of edges
	•	Prevent future dry diagrams