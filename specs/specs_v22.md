You are a senior systems engineer and creative animation architect.

Context:
- The application generates diagrams using PlantUML → SVG.
- SVGs represent technical architectures or structured stories.
- SVGs are rendered inline in the DOM.
- Current CSS-only animations are insufficient (lack uniformity and expressiveness).
- An MCP (Model Context Protocol) system already exists.
- You may register and use additional LLMs as tools via MCP.
- You may use any JS animation libraries (GSAP, anime.js, Web Animations API, etc.).
- You may modify SVG geometry and apply free-form creative animation.

ABSOLUTE CONSTRAINT (NON-NEGOTIABLE):
❗ Animation MUST NOT introduce a new context.
❗ Animation MUST preserve semantic meaning and topology.

Meaning:
- No new nodes, edges, or relationships may be added.
- No existing nodes, edges, or relationships may be removed.
- Animation may elaborate or emphasize structure, but may not invent causality, order, or importance not present in the SVG.
- Final animated state must be topologically equivalent to the original SVG.

---

HIGH-LEVEL GOAL

Build an intelligent animation system that:
- Understands the structure of an existing SVG
- Creatively animates it for clarity and understanding
- Preserves original meaning exactly
- Produces visually coherent, uniform, explainable animations

---

ARCHITECTURE (MANDATORY)

1. Inline SVG (from PlantUML)
2. SVG Structure Analyzer
3. Animation Intelligence LLM (registered via MCP)
4. Animation Plan (free-form but inspectable)
5. Animation Executor (CSS and/or JS)
6. Browser-based validation

---

TASKS

1. SVG Structural Analysis
- Parse inline SVG to extract:
  - Nodes (<g>, <rect>, <text>)
  - Edges (<path>, <line>)
  - Groups / clusters
  - Labels and IDs
- Build a structural graph:
  - Elements
  - Connections
  - Group membership

2. Register Animation Intelligence LLM
- Register a new MCP tool:
  animation_intelligence_llm
- Input to LLM:
  - SVG structural graph
  - Geometry data
  - Diagram type hint (architecture, flow, sequence, story)
- The LLM may:
  - Choose animation styles freely
  - Use motion, transforms, timing, easing
  - Introduce visual metaphors
- The LLM may NOT:
  - Introduce new semantic relationships
  - Alter graph topology

3. Animation Plan Output
- The LLM must output:
  - A structured animation plan (JSON or JS object)
  - Per-element animation decisions
  - Timing and sequencing
- The plan must be human-readable and debuggable.
- Free-form creativity is allowed, but intent must be inspectable.

4. Animation Execution
- Implement animation using:
  - CSS animations and/or
  - JS animation libraries
- Geometry changes are allowed.
- Ensure animations autoplay on render.
- Provide a clean fallback to static SVG.

5. Semantic Invariance Check (MANDATORY)
Before and after animation:
- Compare SVG structure:
  - Same elements
  - Same connections
  - Same groupings
- Fail animation if semantic drift is detected.
- Log exactly what would have changed and abort.

6. Frontend Integration
- Add “Animate” toggle/button.
- animated=false → static SVG
- animated=true → animated SVG
- Animation must run without user interaction beyond toggle.

---

PASSING CRITERIA (ALL MUST PASS)

- Animation is visually expressive (not just fade-in/out).
- Similar components animate consistently.
- No new meaning is implied by animation.
- No elements disappear permanently.
- Final frame preserves original diagram topology.
- Animation works in modern browsers.
- Removing animation code restores original SVG exactly.

---

TEST CASES (REQUIRED)

1. Linear Flow Diagram
User → API → Service → DB
- Animation shows flow and focus.
- No reordering or implied priority beyond structure.

2. Branching Architecture
API → ServiceA, ServiceB
- Animation does not imply ServiceA happens before ServiceB unless structure says so.

3. Large System Diagram
- Groups animate cohesively.
- Non-focused elements de-emphasize but remain visible.

4. Semantic Drift Test
- Compare pre/post SVG structure.
- Any mismatch = FAIL.

5. Regression
- animated=false renders unchanged SVG.
- animated=true renders animated SVG.

---

BROWSER-BASED VALIDATION (MANDATORY)

- Open animated SVG in browser (VSCode / Playwright / Puppeteer).
- Visually confirm animation.
- Programmatically confirm DOM structure invariance.
- Capture evidence (screenshots or DOM logs).

---

SELF-CORRECTION LOOP (MANDATORY)

1. Run all test cases.
2. If ANY test fails:
   - Identify failing layer:
     a) SVG parsing
     b) Animation LLM output
     c) Animation execution
     d) Semantic invariance check
   - Fix ONLY that layer.
3. Re-run all tests.
4. Repeat until ALL tests and criteria pass.
5. Do NOT stop at partial success.

---

DELIVERABLES

- MCP tool registration code
- Animation Intelligence LLM prompt
- Animation plan schema
- Animation execution code
- Semantic invariance checker
- Browser validation scripts
- Root-cause analysis for initial failures

IMPORTANT:
You are optimizing for correctness + expressive clarity.
If animation changes meaning, it is a bug.