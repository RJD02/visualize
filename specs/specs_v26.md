You are a senior systems architect brought in to fix a semantic design flaw.

Context:
- The application generates diagrams from:
  - free-form text
  - stories
  - documents (pdf, docx, txt)
  - GitHub repositories
- The system uses an Intermediate Representation (IR) and renders SVG diagrams.
- Current behavior:
  - IR → SVG generation is inconsistent and lossy
  - Diagrams generated from stories look arbitrary
  - Diagrams generated from repos do not resemble earlier architecture diagrams
  - The assistant frequently asks clarifying questions instead of acting
- This indicates the system does NOT understand:
  - what kind of diagram is expected
  - why the diagram is being generated
  - how different inputs map to different diagram intents

Goal:
Redesign the diagram generation pipeline so that:
1. The system always understands *what diagram to generate*
2. IR faithfully represents meaning, not just structure
3. IR → SVG translation is predictable and consistent
4. Diagrams for the same source evolve coherently (not randomly)
5. The assistant behaves decisively, not ambiguously

---

CORE PROBLEM TO SOLVE (DO NOT SKIP)

The system currently treats all inputs as equivalent.
This is WRONG.

Different inputs require different diagram intents.

You must introduce **Diagram Intent Detection** as a first-class concept.

---

TARGET MENTAL MODEL (NON-NEGOTIABLE)

The pipeline MUST be:

Input
  ↓
Intent Detection (NEW)
  ↓
Intent-Specific Semantic IR (NEW)
  ↓
Structural IR (existing, refined)
  ↓
Renderer (PlantUML / Mermaid / Structurizr)
  ↓
Neutral SVG
  ↓
Aesthetics + Animation (existing)

If intent is missing or unclear, the system must infer a default — NOT ask the user.

---

TASKS

### 1. Introduce Diagram Intent Detection (MANDATORY)

Implement an intent detection step that classifies input into one of:

- system_context (high-level architecture)
- container (services & infrastructure)
- component (internal structure)
- sequence / flow (behavior over time)
- story / narrative (events & transitions)
- generic_summary (fallback)

Rules:
- GitHub repo → default to system_context → container → component
- Architecture text → system_context or container
- Story / prose → story / narrative
- Documents → summary → structure → flow

The assistant must NEVER ask:
“What diagram do you want?”
unless explicitly ambiguous.

---

### 2. Redesign the Semantic IR (CRITICAL)

Your current IR is too generic.

Create **intent-aware IR schemas**, for example:

#### Architecture IR
- actors
- systems
- services
- data stores
- relationships

#### Story IR
- characters
- locations
- events
- transitions
- causality

#### Sequence IR
- participants
- steps
- messages
- ordering

Each IR:
- Must be deterministic
- Must be inspectable (“Show IR” must make sense to a human)
- Must preserve meaning from the input

DO NOT reuse the same IR schema for all intents.

---

### 3. Fix IR → SVG Translation

Currently:
- IR → SVG produces arbitrary layouts
- Visual continuity is lost across generations

Fix this by:
- Ensuring each IR type maps to a specific renderer + diagram type
- Maintaining stable identifiers so diagrams evolve, not reset
- Reusing layout heuristics where possible

Example:
- Same repo → same system_context diagram structure
- “Animate this” → reuse existing diagram + add behavior

---

### 4. Make the Assistant Decisive

Change assistant behavior so that:

- “Create a diagram for this repo” → generates a system/context diagram
- “Animate it” → animates the last relevant diagram
- “Generate a diagram for this story” → produces a narrative flow diagram

The assistant should:
- Infer intent
- Act
- Only ask clarifying questions if multiple intents are equally valid

---

### 5. Enforce Diagram Coherence Across History

When multiple diagrams exist:
- New diagrams must relate to previous ones
- Component diagrams must refine container diagrams
- Sequence diagrams must reference known components

Do NOT generate unrelated diagrams for the same source.

---

TEST CASES (MANDATORY)

### Test 1 — GitHub Repo
Input:
https://github.com/RJD02/job-portal-go
Expected:
- System context diagram
- Followed by container/component diagrams
- Consistent structure across versions

### Test 2 — Architecture Text
Input:
“User → API → Service → DB”
Expected:
- Container or sequence diagram
- Clean, recognizable structure

### Test 3 — Story
Input:
Narrative prose
Expected:
- Event/flow diagram
- Characters and transitions clearly represented
- No random technical boxes

### Test 4 — Evolution
Input:
“Animate this diagram”
Expected:
- Same diagram
- Added behavior
- No re-generation from scratch

---

SUCCESS CRITERIA (POC PASS)

ALL must be true:

- Diagrams visually resemble earlier outputs for the same source
- IR is meaningful when viewed directly
- IR → SVG translation is predictable
- Different input types yield appropriate diagram styles
- The assistant behaves confidently and purposefully
- The system feels intentional, not random

---

SELF-CORRECTION LOOP

If any test fails:
- Identify which layer failed:
  a) intent detection
  b) semantic IR
  c) translation
  d) assistant behavior
- Fix ONLY that layer
- Re-run all tests

---

IMPORTANT PHILOSOPHY

This system does not “draw diagrams”.
It **understands content, decides intent, and explains structure visually**.

If diagrams feel arbitrary, intent is missing.
Fix intent first.


APPENDIX: RENDERER INTEGRATION (MANDATORY)

The current codebase DOES NOT integrate Mermaid or Structurizr.
This must be implemented as part of fixing the IR → SVG pipeline.

This appendix extends the previous prompt and is NOT optional.

---

GOAL (RENDERER LAYER)

Integrate Mermaid and Structurizr as Dockerized, sandboxed diagram renderers,
expose them as MCP tools, and route all diagram generation through them
based on detected diagram intent.

PlantUML remains supported but is no longer the only renderer.

---

NON-NEGOTIABLE DESIGN RULES

1. Mermaid and Structurizr MUST run in Docker containers
2. They MUST be treated as external compilers, not libraries
3. They MUST accept deterministic input generated from IR
4. They MUST output neutral SVG (no aesthetics, no themes)
5. The rest of the system MUST NOT care which renderer was used

---

RENDERER ARCHITECTURE (EXTENSION)

Intent Detection
   ↓
Intent-Specific Semantic IR
   ↓
Structural IR
   ↓
Renderer Router (NEW)
   ↓
Dockerized Renderers
   ├── Mermaid (flow / sequence / story)
   ├── Structurizr (system / container / component)
   └── PlantUML (fallback / UML)
        ↓
Neutral SVG
        ↓
Existing Post-SVG Layers (aesthetics, animation, export)

---

TASKS (RENDERER INTEGRATION)

### 1. Dockerize Mermaid

- Create a Docker image using `@mermaid-js/mermaid-cli`
- The container must:
  - Accept Mermaid syntax via stdin or mounted file
  - Output SVG to stdout or mounted file
- Disable themes and styling
- Ensure deterministic output

Expose one of:
- CLI entrypoint
- Minimal HTTP server

---

### 2. Dockerize Structurizr

- Create a Docker image using Structurizr CLI
- Input:
  - Structurizr DSL or workspace JSON generated from IR
- Output:
  - SVG diagrams
- Enforce:
  - No colors
  - No styles
  - No branding

Expose one of:
- CLI entrypoint
- Minimal HTTP server

---

### 3. Register Renderers as MCP Tools

Register THREE MCP tools:

- `mermaid_renderer`
- `structurizr_renderer`
- `plantuml_renderer`

Each MCP tool must:
- Accept:
  - Structural IR (or translated IR)
- Return:
  - SVG (string or file)
- Be stateless and reproducible
- Log input/output for debugging

---

### 4. Implement Renderer Router (CRITICAL)

Add a renderer routing layer that decides which renderer to use.

Initial routing rules (POC-safe defaults):

- Intent = story / flow / sequence → Mermaid
- Intent = system_context / container / component → Structurizr
- Intent = generic UML / fallback → PlantUML

The router must:
- Be deterministic
- Return:
  - chosen renderer
  - justification (for debugging / Show IR)
- Allow override later (but not now)

---

### 5. Translation Layer (IR → Renderer Input)

Implement deterministic translators:

- Structural IR → Mermaid syntax
- Structural IR → Structurizr DSL / JSON
- Structural IR → PlantUML

Rules:
- Same IR MUST produce same renderer input
- No aesthetics allowed at this stage
- Renderer-specific quirks must be isolated here

---

### 6. Neutral SVG Validation

After rendering:
- Parse SVG
- FAIL if:
  - inline fill/stroke colors exist
  - style tags define color or theme
- Strip or reject non-neutral SVGs

This ensures:
- Pre-SVG aesthetics are fully blocked
- All styling remains post-SVG

---

TEST CASES (RENDERER-SPECIFIC)

### Test A — Mermaid Integration
Input:
Simple story / flow
Expected:
- Mermaid container invoked
- SVG produced
- Neutral output

### Test B — Structurizr Integration
Input:
GitHub repo (job-portal-go)
Expected:
- Structurizr container invoked
- System or container diagram produced
- SVG structure stable across runs

### Test C — Routing Correctness
Same IR with different intent hints:
- Renderer choice changes
- Structural meaning remains

### Test D — Post-SVG Compatibility
Rendered SVG passes unchanged through:
- aesthetic layer
- animation layer
- GIF export

---

SUCCESS CRITERIA (EXTENSION)

ALL must be true in addition to prior success criteria:

- Mermaid and Structurizr run in Docker containers
- They are callable via MCP tools
- Renderer choice is automatic and explainable
- IR remains the single source of truth
- SVG output is neutral and deterministic
- No renderer-specific logic leaks upstream

---

IMPORTANT FINAL NOTE

Mermaid and Structurizr are NOT features.
They are COMPILERS.

If IR changes, renderers adapt.
If renderers change, IR does not.

If this boundary is violated, the design is incorrect.