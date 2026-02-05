You are a senior systems architect building an LLM-driven visualization platform.

Context:
- The system generates diagrams from text, files, or GitHub repos.
- Pipeline currently produces:
  - Structural SVG (via PlantUML)
  - Post-SVG animation
  - Post-SVG aesthetic styling
- Animations and post-SVG aesthetics now work.
- However:
  - Aesthetics are leaking into the pre-SVG layer
  - Chat prompts are not powerful enough
  - There is no formal semantic representation of “visual intent”

Goal:
Redesign the system so that:
1) Chat input influences diagrams through **semantic meaning**, not raw visuals
2) Pre-SVG output is strictly structural (no aesthetics)
3) Aesthetic and animation decisions are driven by a dedicated semantic IR
4) The chat window becomes a high-level “visual intent controller”

---

CORE PRINCIPLE (NON-NEGOTIABLE)

❗ LLMs must NEVER choose concrete visuals (colors, CSS, animation code) directly.
❗ LLMs may ONLY express **semantic aesthetic intent**.
❗ Rendering layers decide HOW intent is visualized.

---

TARGET ARCHITECTURE (MANDATORY)

1. Chat Window (user + system prompts)
2. Semantic Intent LLM (NEW)
3. Semantic Aesthetic IR (NEW)
4. Structural IR (existing)
5. PlantUML (structure only)
6. SVG (neutral baseline)
7. Visual Grammar + Animation Renderer
8. UI + Export

---

TASKS

### 1. Strengthen the Chat Window

Upgrade the chat system so it:
- Accepts prompts like:
  - “Make this calm and minimal”
  - “Highlight critical components”
  - “Reduce visual noise”
  - “Focus attention on data flow”
- Rejects or ignores:
  - Direct color instructions
  - CSS / animation instructions
- Routes chat input to a **Semantic Intent LLM**, not directly to rendering.

---

### 2. Introduce Semantic Aesthetic IR (NEW)

Design and implement a **Semantic Aesthetic IR** that captures intent WITHOUT visuals.

Example schema:

{
  "globalIntent": {
    "mood": "minimal | vibrant | calm | energetic",
    "contrast": "low | medium | high",
    "density": "compact | spacious"
  },
  "nodeIntent": {
    "api_gateway": {
      "importance": "primary",
      "attention": "focus",
      "stability": "stable"
    }
  },
  "edgeIntent": {
    "api_gateway->db": {
      "activity": "active",
      "criticality": "high"
    }
  }
}

This IR:
- Must NOT contain colors, CSS, or animation types
- Must be fully inspectable and debuggable

---

### 3. Enforce a Pure Pre-SVG Layer

Modify the pipeline so that:
- Structural IR → PlantUML contains:
  - ONLY nodes, edges, groups
  - NO skinparams
  - NO colors
  - NO styles
- Pre-SVG output must be visually neutral and boring by design.

Add validation:
- If PlantUML contains any aesthetic directive → FAIL.

---

### 4. Rendering & Animation Consume Semantic IR

Modify rendering so that:
- Visual Grammar Layer maps semantic intent → visuals
- Animation layer uses:
  - importance
  - attention
  - activity
- Different semantic intents result in visibly different aesthetics
  (e.g., minimal vs vibrant), without changing structure.

---

### 5. Make Chat “Stronger” Safely

Implement guardrails so that:
- Chat controls *intent*, not appearance
- Same structure + different chat intent → different aesthetics
- Same chat intent + different structure → consistent visual grammar

---

TEST CASES (MANDATORY)

### Test 1 — Pre-SVG Purity
Input:
- Any diagram
Expected:
- PlantUML output contains zero aesthetic directives
- SVG baseline is neutral

### Test 2 — Semantic Intent Influence
Chat:
- “Make this calm and minimal”
Expected:
- Semantic Aesthetic IR reflects calm/minimal
- Enhanced SVG is visibly calmer than baseline

### Test 3 — Contrast Change
Chat:
- “Highlight critical paths”
Expected:
- Semantic IR marks critical edges/nodes
- Rendered SVG emphasizes those paths visually

### Test 4 — Animation Coordination
Chat:
- “Focus on data flow”
Expected:
- Animation emphasizes edges with activity=active
- Nodes de-emphasize appropriately

### Test 5 — Regression
- Remove Semantic Aesthetic IR
- Rendering falls back to default neutral style

---

SUCCESS CRITERIA (POC PASS CONDITIONS)

ALL must be true:

- Pre-SVG diagrams are purely structural.
- Visual differences are clearly observable post-SVG.
- Chat input influences diagrams meaningfully without visual leakage.
- Aesthetic decisions are explainable via Semantic IR.
- Animation and aesthetics align with semantic intent.
- Exported GIF reflects semantic aesthetics correctly.

---

SELF-CORRECTION LOOP (MANDATORY)

- If any test fails:
  - Identify which layer leaked responsibility:
    a) Chat
    b) Semantic IR
    c) Structural IR
    d) Rendering
  - Fix ONLY that layer.
- Repeat until all tests and success criteria pass.

---

IMPORTANT PHILOSOPHY

This system is NOT letting users or LLMs “design diagrams”.
It is letting them express **what should matter**, and letting the system decide how that is shown.

If intent and visuals are mixed, the design is wrong.