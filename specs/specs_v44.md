Prompt for Codex — Handle Dense Architecture Diagrams Gracefully

You are upgrading the diagram generation engine to prevent “hairball” graphs in large infrastructure and component diagrams.

The problem:
When many actors or systems connect to many components with generic relations like “interacts with”, the diagram becomes unreadable due to excessive edge crossings.

Your task:
Introduce structural constraints, relationship normalization, and layout strategies to produce readable, enterprise-grade diagrams.

⸻

1️⃣ Relationship Normalization Rules (IR Layer Fix)

Modify IR generation so that:
	1.	Do NOT generate N×M generic edges.
	•	If 3 user roles all connect to Kubernetes via identical relation type (“interacts with”), collapse them into:
	•	A single grouped actor node
	•	OR a shared gateway abstraction
	2.	Introduce “Interaction Hub” pattern:
	•	Users → Ingress → Cluster
	•	NOT Users → Every internal component
	3.	Replace generic “interacts with” with specific semantics:
	•	routes_to
	•	consumes
	•	produces
	•	manages
	•	authenticates_via
	•	replicates_to
	•	monitors
	•	stores_in

If relation is vague → route via intermediary layer.

⸻

2️⃣ Introduce Layered Layout Constraints

Enforce strict vertical or horizontal layering:

Example for Infrastructure View:

Layer 1: Users
Layer 2: Ingress / Gateway
Layer 3: Application Layer (K8s clusters)
Layer 4: Data Layer (Object Store, DB)
Layer 5: DR Layer

Edges must:
	•	Only connect to adjacent layers
	•	Avoid skipping layers
	•	Never create long cross-diagonal edges if avoidable

⸻

3️⃣ Edge Reduction Strategy

If node A connects to 8 components inside node B’s cluster:

Replace:
A → X
A → Y
A → Z
A → …

With:
A → Cluster
Cluster internally connects to X/Y/Z

Implement rule:
External actors cannot connect to internal sub-components directly unless explicitly required.

⸻

4️⃣ Automatic Edge Crossing Minimization

Implement layout-aware constraints:
	•	Use hierarchical layout (Dagre / ELK / Graphviz dot)
	•	Prefer top-down layout for infra
	•	Enforce same-rank grouping
	•	Cluster related components visually
	•	Use subgraphs for zones

If using PlantUML:
	•	Use package blocks
	•	Use left-to-right direction inside layers
	•	Avoid bidirectional arrows unless required

⸻

5️⃣ Zone-Based Rendering Rules

If IR contains zones:
	•	Render zones as large containers
	•	Edges should enter zone at one entry point
	•	Avoid direct node-to-node cross-zone edges

Add optional:
zone_entry_node abstraction for each zone

⸻

6️⃣ Edge Label Deduplication

If 6 edges have same label and same source:

Combine into:
A → [X,Y,Z] (via group edge)
OR
Use a summary label:
“Interacts with application services”

⸻

7️⃣ IR Enhancement

Extend IR schema with:

{
“layoutHints”: {
“layer”: 1,
“avoidCrossing”: true,
“preferredDirection”: “down”
},
“interactionPolicy”: {
“collapseGenericEdges”: true,
“enforceGatewayRouting”: true,
“maxEdgesPerNode”: 5
}
}

⸻

8️⃣ Visual Cleanliness Rules

Implement:
	•	Max 3 outgoing edges per node before collapsing
	•	Hide labels for obvious relationships
	•	Use consistent arrow style per relation type
	•	Thicker edges only for replication / critical flows
	•	Use curved edges only when necessary

⸻

9️⃣ Cypress Test Cases (Automated Validation)

Write Cypress tests that:

Test 1:
Generate infrastructure diagram from large prompt.
Assert:
	•	Total edges < 40
	•	No node has > 6 outgoing edges
	•	No duplicate edge labels from same source

Test 2:
Check that Users do NOT connect directly to internal storage components.

Test 3:
Ensure all nodes are inside declared zones.

Test 4:
Check that diagram direction is consistent (top-down or left-right only).

If failing → log structural reason and fail test.

⸻

🔁 Feedback Loop

After generation:
	•	Compute edge density score
	•	If density > threshold → auto-trigger IR simplification pass
	•	Regenerate diagram

⸻

🎯 Success Criteria

A large infrastructure diagram must:
	•	Clearly show hierarchy
	•	Avoid edge spaghetti
	•	Have readable groupings
	•	Avoid redundant generic relations
	•	Maintain semantic correctness

⸻

🧠 Important Insight

Your issue is not rendering.

It is:

You are drawing logical truth instead of architectural abstraction.

Enterprise diagrams are not literal graphs.
They are curated abstractions.

Your engine must learn abstraction.