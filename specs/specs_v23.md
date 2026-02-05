You are a senior frontend + visualization engineer with design intelligence.

Context:
- The application generates diagrams using PlantUML → SVG.
- SVG diagrams now:
  - Render correctly
  - Animate correctly
  - Export correctly to GIF
- Current visuals are functionally correct but visually neutral.
- This POC will be considered PASSED only if:
  - The system can intentionally improve visual aesthetics
  - Differences are observable between pre-SVG and post-SVG rendering
  - Visual changes are consistent and justifiable

There is NO user prompt yet.
For now, the LLM must decide what looks best.

---

GOAL

Introduce an **Aesthetic Intelligence step** that:
- Analyzes the generated SVG
- Decides how to improve visual appeal
- Applies controlled visual changes
- Preserves semantic meaning
- Produces a visibly improved diagram

This must work BOTH:
- As static SVG
- As animated SVG
- In exported GIF

---

HIGH-LEVEL PIPELINE (MANDATORY)

1. Input (text / repo / files)
2. PlantUML → Base SVG (baseline)
3. SVG Structural Analyzer
4. Aesthetic Intelligence LLM (NEW)
5. Aesthetic Plan (structured)
6. SVG Style Transformer
7. Animation Executor (existing)
8. UI + Export

---

AESTHETIC INTELLIGENCE LLM (NEW)

Register a new MCP tool:
  aesthetic_planner_llm

Input:
- Parsed SVG structure
- Element types (node, edge, cluster)
- Diagram size and density
- Animation presence (yes/no)

The LLM may:
- Choose color palette strategy:
  - minimalist
  - high-contrast
  - category-based
- Adjust:
  - fill colors
  - stroke colors
  - stroke widths
  - font weights
  - background contrast
- Decide emphasis strategy:
  - important nodes pop
  - secondary nodes de-emphasized
- Coordinate aesthetics with animation

The LLM may NOT:
- Add or remove elements
- Change labels or topology
- Introduce new semantics

---

AESTHETIC PLAN OUTPUT (STRICT)

The LLM must output a structured plan ONLY:

{
  "theme": "minimalist" | "high-contrast" | "vibrant",
  "background": "#ffffff",
  "nodeStyles": {
    "default": { "fill": "...", "stroke": "...", "strokeWidth": 1 },
    "highlight": { "fill": "...", "stroke": "...", "strokeWidth": 2 }
  },
  "edgeStyles": {
    "default": { "stroke": "...", "strokeWidth": 1 },
    "active": { "stroke": "...", "strokeWidth": 2 }
  },
  "font": {
    "family": "system-ui",
    "weight": "normal"
  }
}

No CSS. No prose.

---

SVG STYLE TRANSFORMATION

- Apply aesthetic plan by:
  - Injecting <style> into SVG
  - Or modifying element attributes
- Ensure:
  - Pre-SVG (baseline) is preserved for comparison
  - Post-SVG (styled) is clearly different
- Style changes must affect visible primitives:
  - <rect>, <path>, <text>, etc.

---

UI REQUIREMENTS (MANDATORY)

1. Show TWO states:
   - Baseline SVG (unstyled)
   - Enhanced SVG (styled + animated)
2. Provide a toggle:
   - “Original”
   - “Enhanced”
3. Export GIF must export the ENHANCED version only.

---

PASSING CRITERIA (POC SUCCESS DEFINITION)

ALL must be true:

- Visual difference between baseline and enhanced SVG is immediately noticeable.
- Enhanced version improves:
  - clarity
  - visual hierarchy
  - focus
- Animation and aesthetics complement each other.
- No semantic or structural changes occurred.
- Exported GIF reflects enhanced aesthetics.

---

HARD TEST CASES (MANDATORY)

1. Dense Diagram
- Expect muted palette + clear hierarchy.

2. Small Diagram
- Expect bolder contrast and emphasis.

3. Animated Flow
- Active edges/nodes visually stand out.

4. Regression
- Switching back to baseline restores original look exactly.

---

BROWSER-BASED VALIDATION (REQUIRED)

- Load baseline SVG → screenshot
- Load enhanced SVG → screenshot
- Compare visually (human-visible difference)
- Export GIF → confirm colors + animation persist

---

SELF-CORRECTION LOOP (MANDATORY)

- If enhanced SVG is not visibly better:
  - Revise aesthetic plan
  - Reapply styles
- If aesthetics reduce clarity:
  - Simplify palette
- Repeat until POC criteria are met.

---

IMPORTANT PRINCIPLE

This system is NOT decorating diagrams.
It is applying intentional visual design to improve understanding.

If improvement is not obvious to a human viewer, the task is NOT done.