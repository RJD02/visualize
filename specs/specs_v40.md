You are a senior engineer tasked with integrating a new architecture quality analysis feature into the diagram platform. This feature must evaluate the quality of the architecture described by an IR. It must produce a structured report describing measurable architectural attributes, detect potential issues, and generate suggested IR patch operations that the user can apply manually. This feature must be informational + actionable, not automated refactoring. It will be implemented as a new agent in the system: architecture_quality_agent.

Design the agent according to the following requirements:
	1.	Input/Output Context
	•	Input: a fully enriched IR object representing a diagram.
	•	Output: a structured architecture quality report that includes:
	•	metrics describing architectural characteristics,
	•	a list of detected issues with severity,
	•	an overall quality score,
	•	context for each issue,
	•	optional suggested IR patch operations to address each issue,
	•	confidence scores.
	2.	Degree of Determinism
	•	Compute structural metrics deterministically (e.g. cycle detection, dependency fan-in/out, coupling/clustering, layering violations) before involving the LLM. Do not let the LLM invent metrics; it should interpret structured data and explain them. For example, reduce coupling or high cohesion improves design quality, following established software design principles. Coupling and cohesion are key indicators of architecture quality.  ￼
	3.	Architecture Quality Dimensions
The report should include, at minimum:
	•	Structural Integrity: detect cycles in dependency graph.
	•	Coupling & Cohesion Signals: modules with high incoming/outgoing edges, low internal cohesion.
	•	Layering Discipline: violations where higher-level components access lower layers directly instead of through services.
	•	Centrality Risk: if a single node has dangerously high coupling (God module risk).
	•	Scalability & Maintainability Indicators: metrics that reflect likely technical debt signals (complex dependencies between modules). Use deterministic graph analysis where possible.
	4.	Issue Detection
For each detected architectural concern:
	•	Generate a structured entry that includes:
	•	issue id,
	•	description,
	•	severity (high/medium/low),
	•	metric values that triggered it,
	•	confidence range.
	5.	Score Calculation
	•	Aggregate metrics into a simple overall score (e.g. 0–100) using normalized values of structural and dependency metrics.
	•	The scoring function must be deterministic and explainable.
	6.	Suggested IR Patch Operations
	•	For each detected issue, produce suggested patch operations that can improve the architecture if applied by the user.
	•	A patch should be expressed in the same patch ops format as your IR editor expects (e.g., remove_edge, add_interface_node, add_edge via abstraction) and must be clearly associated with the issue it addresses.
	7.	Interpretation Layer (LLM Assisted)
	•	After computing raw metrics, the agent should call the LLM with a structured prompt containing:
	•	IR summary,
	•	computed metrics,
	•	list of detected metric-based issues,
	•	goals (“explain what each potential architecture concern means and how the suggested patches relate to improving quality”).
	•	The LLM should produce natural language explanations aligned with the structured report without altering the underlying metrics or inventing unsupported suggestions.
	8.	Constraints and Safety
	•	Do not perform autonomous refactors; suggestions must be explicitly connectable to IR patch ops that the user must approve.
	•	Ensure metrics do not depend on subjective opinions; keep the LLM’s role to interpretation, not metric generation.
	•	Avoid hallucination: if the LLM cannot confidently explain or align suggestions with metrics, the agent must provide a fallback structured explanation (e.g. “no actionable path identified”).
	9.	Agent Integration
	•	Register the architecture_quality_agent with the MCP server under a clear capability name (e.g., analyze_architecture_quality).
	•	Define the contract so other agents can call it:
	•	Input: { "ir": {...}, "context": "...optional..." }
	•	Output: { "score": number, "issues": [...], "suggested_patches": [...], "explanations": [...] }
	10.	UI Contract

	•	Ensure the frontend has a route to request architecture analysis and that the returned report integrates with the diagram viewer.
	•	The UI must allow users to view each issue, read explanations, and preview suggested IR patch effects before accepting.

	11.	Tests and Validation

	•	Add deterministic test cases for:
	•	cycle detection,
	•	high coupling scenario,
	•	layering violation,
	•	god module detection,
	•	no issues case.
	•	Add tests that the agent returns valid JSON schema with expected fields.

	12.	Documentation

	•	Write clear documentation for this agent’s behavior, preferred metrics, and how suggested patches can address issues.
	•	Describe how the score is computed and how severity levels are determined.

The objective is to integrate an informative + actionable architecture scoring layer into the platform that helps users understand where their architecture may be weak and how they can improve it via controlled IR patches.

⸻
