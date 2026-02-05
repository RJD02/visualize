You are a senior systems engineer and debugging specialist.

Context:
- The application generates diagrams using PlantUML.
- Output is currently SVG.
- An animation layer (CSS-based) is injected by an agent.
- The UI shows an “Animate” toggle and claims “Inline SVG”.
- Despite this, no animation is visible in the browser.

Goal:
Identify WHY SVG animations are not working, and fix the system from the ground up.
Do NOT assume animation logic is correct. Prove each layer works.

---

MANDATORY DEBUGGING STEPS (DO NOT SKIP)

1. Verify SVG Embedding Mode
- Inspect frontend rendering.
- Determine whether SVG is:
  a) inline <svg> in DOM
  b) <img src="...">
  c) <object> or <embed>
- If NOT inline:
  - Refactor frontend to fetch SVG as text and inject via innerHTML.
  - Document why CSS animations do not work on non-inline SVG.

2. Verify CSS Injection
- Confirm that:
  - <style> tag exists inside the <svg>.
  - CSS rules are valid and syntactically correct.
- Inject a temporary universal animation:
  svg g { animation: debugblink 1s infinite alternate; }
- If this does NOT animate, explain why and fix injection location.

3. Verify Selector Accuracy
- Extract all <g> element IDs from the SVG.
- Compare these IDs with selectors used in animation CSS.
- If mismatched:
  - Update animation plan to use exact SVG IDs.
  - Do NOT infer IDs from text labels.

4. Verify SVG Animation Semantics
- Ensure all animations use SVG-safe CSS:
  - opacity
  - stroke / stroke-width
  - stroke-dasharray / stroke-dashoffset
  - transform ONLY with:
    transform-box: fill-box;
    transform-origin: center;
- Replace any unsupported animation logic.

5. Verify Runtime Effect
- Programmatically apply a visible style change:
  document.querySelector("svg g").style.opacity = 0.2
- If no visual change occurs:
  - Explain why DOM manipulation is not affecting the SVG.
  - Fix the rendering pipeline.

---

ROOT-CAUSE ANALYSIS (REQUIRED OUTPUT)

After debugging, explicitly answer:
- Which layer was broken?
  a) frontend embedding
  b) CSS injection
  c) selector mismatch
  d) SVG animation semantics
- Why the system *appeared* correct but was not.
- Why the bug was silent (no errors).

---

FIX IMPLEMENTATION REQUIREMENTS

- Refactor code so that:
  - Static SVG renders correctly.
  - Animated SVG renders and animates deterministically.
- Keep animation as a post-processing step.
- Do NOT introduce JS animation libraries.
- Preserve non-animated SVG usability.

---

VALIDATION CRITERIA (ALL MUST PASS)

- Static SVG renders when animated=false.
- SVG animates visibly when animated=true.
- Animation works in Chrome and Firefox.
- SVG remains readable when CSS animation is removed.
- Debug animation (blink test) works before custom animation.

---

ITERATION LOOP (MANDATORY)

- If ANY validation criterion fails:
  - Identify failing layer.
  - Fix ONLY that layer.
  - Re-run validation.
- Repeat until all criteria pass.
- Do NOT stop at partial success.

---

DELIVERABLES

- Root-cause explanation (plain English).
- Code changes (backend + frontend).
- Example working animated SVG snippet.
- Comments explaining why the fix works.

IMPORTANT:
This task is about correctness and architecture, not visual polish.
If you cannot prove a layer works, treat it as broken.