You are a senior systems architect and infrastructure engineer.

Context:
- The application generates diagrams from:
  - text
  - files (pdf, docx, txt)
  - GitHub repositories
- The system already uses:
  - an Intermediate Representation (IR) for structure
  - post-SVG aesthetics
  - post-SVG animation
- The long-term goal is to support multiple diagram engines deterministically.
- For this POC, efficiency and correctness matter more than completeness.

Goal:
Integrate Mermaid and Structurizr as Dockerized diagram renderers, expose them as MCP tools, and route diagram generation through a shared IR so that:
- Multiple renderers can be used interchangeably
- The agent decides which renderer to use
- Output is deterministic and neutral (no aesthetics)
- Post-SVG layers remain unchanged

---

CORE DESIGN PRINCIPLES (NON-NEGOTIABLE)

1. IR is the source of truth
   - All renderers consume IR (or a deterministic translation of it)
   - No renderer-specific logic leaks upstream

2. Renderers are compilers, not libraries
   - Mermaid, Structurizr, PlantUML run in Docker
   - They are stateless and sandboxed

3. Renderers must output neutral SVG
   - No colors
   - No themes
   - No styling decisions
   - All aesthetics happen post-SVG

4. Renderer choice is a decision, not a constant
   - The agent must decide which renderer to use
   - Decision must be explainable and testable

---

TARGET ARCHITECTURE

IR (common, neutral)
   ↓
Renderer Router
   ↓
Dockerized Renderers
   ├── Mermaid
   ├── Structurizr
   └── PlantUML
        ↓
Neutral SVG
        ↓
Aesthetic + Animation Layers (existing)

---

TASKS

### 1. Define a Minimal, Practical IR (POC-Level)

Design a shared IR that can be translated into:
- Mermaid syntax
- Structurizr DSL / workspace
- PlantUML

The IR must:
- Represent nodes, edges, groups
- Be deterministic
- Avoid renderer-specific concepts

Example (illustrative, refine as needed):

{
  "nodes": [
    { "id": "user", "kind": "person" },
    { "id": "api", "kind": "service" },
    { "id": "db", "kind": "database" }
  ],
  "edges": [
    { "from": "user", "to": "api", "type": "interaction" },
    { "from": "api", "to": "db", "type": "data-flow" }
  ],
  "groups": []
}

This IR will evolve later; optimize for POC velocity now.

---

### 2. Dockerize Mermaid

- Create a Docker image using mermaid-cli.
- Input: Mermaid (.mmd) generated from IR.
- Output: SVG.
- Disable or strip all themes and styles.
- Expose a simple CLI or HTTP interface.

---

### 3. Dockerize Structurizr

- Create a Docker image using Structurizr CLI.
- Input: Structurizr DSL or workspace JSON generated from IR.
- Output: SVG diagrams.
- Ensure:
  - No colors
  - No styling directives
- Expose a CLI or HTTP interface.

---

### 4. Register Renderers as MCP Tools

Register each renderer as an MCP tool:

- mermaid_renderer
- structurizr_renderer
- plantuml_renderer

Each tool must:
- Accept IR (or translated IR)
- Return SVG
- Be stateless
- Log inputs and outputs for debugging

---

### 5. Implement Renderer Router (Decision Logic)

Implement a routing layer that decides which renderer to use based on IR.

Example heuristics (initial, refine later):
- Sequence / flow / story-like IR → Mermaid
- Architecture / system / codebase IR → Structurizr
- Generic UML → PlantUML

The router must:
- Be deterministic
- Return which renderer was chosen and why
- Allow easy override later

---

### 6. Translation Layer (IR → Renderer Input)

Implement translators:
- IR → Mermaid syntax
- IR → Structurizr DSL / workspace
- IR → PlantUML

Rules:
- Translation must be deterministic
- Same IR → same output
- No aesthetic leakage

---

### 7. Neutral SVG Validation

After rendering:
- Inspect SVG
- Fail if:
  - inline colors exist
  - style tags define colors
  - themes are applied

Strip or reject non-neutral SVGs.

---

TEST CASES (MANDATORY)

### Test 1 — Determinism
- Same IR rendered twice → identical SVG output.

### Test 2 — Renderer Routing
- Flow-like IR → Mermaid chosen.
- Architecture-like IR → Structurizr chosen.

### Test 3 — Neutral Output
- SVG contains no color fills or strokes except defaults.

### Test 4 — Post-SVG Compatibility
- Neutral SVG passes through existing:
  - aesthetic layer
  - animation layer
  - GIF export

### Test 5 — Renderer Swap
- Same IR rendered via different engines
- Structure equivalent (even if layout differs).

---

SUCCESS CRITERIA (POC PASS)

ALL must be true:

- Mermaid and Structurizr run in Docker containers.
- They are registered and callable via MCP.
- Renderer selection is automatic and explainable.
- IR is the single source of truth.
- SVG output is neutral and deterministic.
- Existing post-SVG animation and aesthetics work unchanged.

---

SELF-CORRECTION LOOP (MANDATORY)

- If any test fails:
  - Identify which layer failed:
    a) IR
    b) Translation
    c) Renderer container
    d) Routing logic
  - Fix ONLY that layer.
- Repeat until all tests pass.

---

IMPORTANT PHILOSOPHY

This system is not “using Mermaid or Structurizr”.
It is compiling diagrams through interchangeable backends using a shared IR.

If renderer-specific logic leaks upstream, the design is wrong.