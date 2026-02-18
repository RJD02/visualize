# Architecture Quality Agent (architecture_quality_agent)

Purpose
-------
Provide deterministic architectural analysis for IRs, surface measurable metrics,
detect structural issues, and propose explicit IR patch operations the user can
apply manually. The agent is informational and never performs automatic refactors.

Contract
--------
- Input: { "ir": {...}, "context": "optional" }
- Output: {
  "score": number,            # 0-100 deterministic score
  "metrics": {...},
  "issues": [...],
  "suggested_patches": [...],
  "explanations": [...],
  "confidence": [low, high]
}

Deterministic Metrics
---------------------
- Structural Integrity: cycle detection using graph algorithms (`networkx.simple_cycles`).
- Coupling: per-node in/out degree, average degree, and `max_degree_ratio`.
- Centrality Risk: degree and betweenness centrality to flag God modules.
- Layering Discipline: nodes may carry a `layer` attribute (integer). Edges that skip >1 layer are flagged.
- Cohesion Signals: if nodes include `members` or `components`, we surface a cohesion estimate (heuristic).

Score Calculation
-----------------
Score is deterministic and explainable. Components:
- cycles (35% weight)
- avg coupling (25% weight)
- centrality (25% weight)
- layering violations (15% weight)

Each metric is normalized to [0,1] where 1 is worst; score = 100 * (1 - weighted_badness).

Issue Entries
-------------
Each issue contains:
- `id` (e.g., `CYCLE_DETECTED`)
- `description`
- `severity` (high/medium/low)
- `metrics` (metric values that triggered the issue)
- `confidence` (range)

Suggested IR Patch Operations
-----------------------------
Suggested patches are advisory and expressed in the IR patch-op style used by the editor. Examples:
- { op: "remove_edge", source: "A", target: "B", explanation: "Break cycle" }
- { op: "extract_interface", node: "Svc", new_node: "Svc_interface", explanation: "Reduce coupling" }
- { op: "add_abstraction", between: ["UI","DB"], explanation: "Respect layering" }

LLM Integration
---------------
The agent prepares a structured prompt containing an IR summary, computed metrics, and detected issues.
The LLM's role is interpretation and explanation only; the agent will not allow the LLM to invent new metrics
or unsupported fixes. If the LLM cannot align explanations to metrics, a deterministic fallback explanation is returned.

Integration / Registration
--------------------------
- Register on the MCP server under capability `analyze_architecture_quality`.
- Input contract: `{ "ir": {...}, "context": "optional" }`
- Output contract: as described above.

UI Contract
-----------
- Frontend route: `/analysis/architecture-quality` (suggested).
- The UI presents: overall `score`, list of `issues`, each issue's `explanations`, and `suggested_patches`.
- The UI must allow previewing a patch's effect and require explicit user approval before applying patches.

Tests
-----
Deterministic tests must cover:
- cycle detection
- high coupling scenario
- layering violation
- god module detection
- no issues case

Files Added
-----------
- `backend-python/src/architecture_quality_agent.py` — core implementation
- `tests/test_architecture_quality_agent.py` — unit tests

Notes
-----
- The agent uses `networkx` for graph analysis; ensure the runtime environment includes this package.
- The agent is intentionally conservative; any LLM-assisted explanations are additional context only.
