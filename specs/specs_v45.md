Semantic Clustering of Disconnected Components

You are upgrading the diagram generation engine to prevent disconnected, hanging, or semantically isolated components in large architecture diagrams.

Problem:
When many components do not share explicit edges or are loosely connected, they appear visually isolated and disconnected. This reduces clarity and architectural meaning.

Goal:
Automatically cluster related components into meaningful semantic groups before rendering.

⸻

1️⃣ Introduce Semantic Clustering Phase in IR Pipeline

Before rendering:

Add a clustering step:

cluster_ir(ir) → enhanced_ir_with_groups

Clustering must happen before layout.

⸻

2️⃣ Clustering Rules

Group nodes into higher-level logical categories based on:

A. Name-based semantic signals
Examples:

If label contains:
	•	“Postgres”, “DB”, “Metadata” → group under “Metadata Layer”
	•	“Kafka”, “CDC” → group under “Streaming Layer”
	•	“Spark”, “Trino” → group under “Compute Layer”
	•	“Object Store”, “Iceberg” → group under “Storage Layer”
	•	“Superset”, “BI” → group under “Analytics Layer”
	•	“Vault” → group under “Security Layer”
	•	“Observability” → group under “Monitoring Layer”

B. Role from IR (if available)
If nodeIntent.type exists:
	•	data_store → Storage
	•	service → Compute
	•	external → External Integrations
	•	security → Security
	•	observability → Monitoring

C. Relation-based proximity
If 2+ nodes connect to the same upstream node,
group them under a shared logical parent.

⸻

3️⃣ Replace Flat Nodes With Container Nodes

Instead of rendering:

Spark
Trino
Airflow

Render:

Compute Layer
	•	Spark
	•	Trino
	•	Airflow

Implementation:

Add synthetic container nodes:

{
“id”: “compute_layer”,
“type”: “group”,
“synthetic”: true
}

Move children inside this group.

Edges should:
	•	connect to group entry node if possible
	•	avoid connecting external actors directly to leaf nodes

⸻

4️⃣ Avoid Over-Fragmentation Rule

If number of isolated nodes > 5:

Trigger clustering automatically.

If number > 8:

Collapse into mandatory grouped structure.

⸻

5️⃣ Group Rendering Rules

Render clusters visually as:
	•	light background container
	•	titled section
	•	minimal border
	•	consistent layout direction

Example zones:

Security Layer
Compute Layer
Storage Layer
Streaming Layer
Metadata Layer
Observability Layer

⸻

6️⃣ Edge Routing Adjustment

When grouping:

If A connects to Spark and Trino:

Replace:
A → Spark
A → Trino

With:
A → Compute Layer

Compute Layer internally contains Spark & Trino.

⸻

7️⃣ Layout Policy

After clustering:

Apply layered layout:

Users
Ingress
Application Layer
Compute Layer
Data Layer
Observability
Security

No free-floating nodes allowed unless explicitly marked “external isolated”.

⸻

8️⃣ Cypress Validation Tests

Test 1:
Generate infra diagram.
Assert:
	•	No more than 3 isolated nodes.
	•	At least 70% of nodes belong to a group container.

Test 2:
Verify groups have titles (Compute, Storage, etc.)

Test 3:
Ensure no leaf node without either:
	•	an incoming edge
	•	or membership inside a group

⸻

9️⃣ Success Criteria

Diagram must:
	•	Avoid spaghetti
	•	Avoid isolated fragments
	•	Have meaningful architectural layers
	•	Tell a story from top to bottom

⸻

🧠 Important Insight

Enterprise diagrams are not literal graphs.

They are:

Layered abstractions.

When components look disconnected,
the abstraction level is wrong.

Fix abstraction before fixing layout.
