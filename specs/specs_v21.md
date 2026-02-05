You are a senior full-stack engineer and autonomous coding agent.

Context:
- The application accepts:
  1) plain text (story / explanation)
  2) files (pdf, docx, txt)
  3) a GitHub repo link (e.g. https://github.com/RJD02)
- Current pipeline: input → PlantUML → PNG
- Goal: upgrade to SVG + post-processed animation (CSS-based)

High-level Objective:
Generate SVG diagrams using PlantUML, and enable deterministic, CSS-based animation that plays when the user clicks an “Animate” button.

---

TASKS

1. PlantUML SVG Output
- Modify the rendering pipeline to generate SVG instead of PNG.
- Ensure SVG has:
  - stable viewBox
  - grouped <g> elements
  - text/title metadata preserved

2. SVG Analysis
- Parse the generated SVG to identify:
  - nodes (groups with text/title)
  - edges (paths / lines connecting nodes)
- Extract bounding boxes and coordinates for ordering.

3. Animation Plan Inference
- Infer a simple, explainable animation plan:
  - Sequential node highlighting
  - Sequential edge flow animation
- Ordering rules (in priority):
  1) Explicit labels like step1, step2 if present
  2) Left-to-right layout
  3) Top-to-bottom layout
- Represent the plan as a JSON structure (steps + timing).

4. CSS Animation Injection
- Inject CSS directly into the SVG <style> tag.
- Allowed animated properties ONLY:
  - opacity
  - stroke
  - stroke-width
  - stroke-dasharray / stroke-dashoffset
  - transform: scale (small emphasis only)
- Do NOT modify geometry or layout.
- Map animation-plan steps to CSS classes.

5. API Changes
- Implement:
  GET /api/diagram/render?format=svg&animated=true|false
- animated=false → static SVG
- animated=true → SVG with injected CSS animations

6. Frontend Changes
- Render static SVG by default.
- Add an “Animate” button or toggle.
- On click, reload SVG with animated=true.
- No JS animation libraries allowed.

7. Modularity
Implement the following modules clearly:
- svgParser
- animationPlanGenerator
- cssInjector
- diagramRenderer

---

ELIGIBILITY CRITERIA (Definition of Done)

A solution is correct ONLY IF:
- Static SVG renders correctly when animated=false.
- Animated SVG plays automatically in a modern browser when animated=true.
- Animation sequence is deterministic across runs.
- SVG remains readable and usable with animation disabled.
- No JavaScript-based animation libraries are introduced.
- No layout shifts or node repositioning occur during animation.
- Code is modular and readable with clear comments.

---

TEST CASES

1. Simple Flow Diagram
Input:
User → API → Service → DB
Expected:
- Nodes highlight in order.
- Edges animate between highlights.

2. Branching Diagram
Input:
User → API → (ServiceA, ServiceB)
Expected:
- API highlights first.
- Both outgoing edges animate sequentially.
- Both services highlight after.

3. No Explicit Order Labels
Input:
Unlabeled nodes
Expected:
- Order inferred via left-to-right / top-to-bottom.

4. Animated Toggle Off
- animated=false returns SVG with NO animation CSS.
- SVG visually identical to animated=true at frame 0.

5. Regression
- PNG pipeline remains unaffected.
- Existing inputs still render diagrams.

---

SELF-CORRECTION LOOP (MANDATORY)

After implementation:
1. Run all test cases mentally or via code.
2. If ANY eligibility criterion fails:
   - Identify the failing module.
   - Refactor ONLY that module.
   - Re-run validation.
3. Repeat until ALL criteria pass.
4. Do NOT stop at partial success.

---

CONSTRAINTS

- No external animation libraries.
- No semantic changes to PlantUML.
- No GIF export in this phase.
- Prefer correctness and explainability over visual flair.

---

DELIVERABLES

- Backend code changes
- Frontend toggle implementation
- Sample injected CSS animation
- Inline comments explaining animation inference logic