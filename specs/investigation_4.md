You are a senior frontend + SVG rendering engineer.

This task CANNOT be solved by code inspection.
You MUST run the real application UI and verify animation at runtime.

Repository:
https://github.com/RJD02/job-portal-go

Goal:
Make SVG animations visibly work in the actual UI.

---

MANDATORY SETUP

1. Clone the repository.
2. Run the backend and frontend exactly as documented.
3. Open the UI in a real browser (VSCode browser, Playwright, or Puppeteer).

DO NOT modify code yet.

---

PHASE 1 — EMPIRICAL OBSERVATION

1. Navigate to the screen that renders the SVG diagram.
2. Toggle “Animate”.
3. Confirm visually:
   - No animation is visible.

4. Open DevTools and inspect the SVG.

Record:
- Is SVG inline (<svg>)?
- Does it contain <style>?
- Which elements are visible:
  - <rect>, <path>, <text>, etc.

---

PHASE 2 — PAINTABILITY TEST (CRITICAL)

In DevTools Console, run:

1. document.querySelectorAll("svg g").length
2. document.querySelectorAll("svg rect").length
3. document.querySelectorAll("svg path").length

Then run:

```js
document.querySelector("svg g").style.opacity = "0.2"

If NOTHING changes visually:
	•	Conclude that animating  is ineffective.

Now run:

document.querySelector("svg rect").style.fill = "red"
document.querySelector("svg path").style.stroke = "red"

If this changes visually:
	•	Conclude that animations must target primitives, not groups.

WRITE THIS CONCLUSION DOWN.

⸻

PHASE 3 — FORCED ANIMATION PROOF

Manually inject:

document.querySelectorAll("svg path").forEach(p => {
  p.style.strokeDasharray = "5 5";
  p.style.animation = "flow 1s linear infinite";
});

const style = document.createElement("style");
style.textContent = `
@keyframes flow {
  from { stroke-dashoffset: 20; }
  to { stroke-dashoffset: 0; }
}
`;
document.querySelector("svg").appendChild(style);

If THIS animates:
	•	CSS is working
	•	SVG is animatable
	•	Current code targets wrong elements

If this STILL does not animate:
	•	Identify what layer is blocking (React re-render, iframe, shadow DOM).

⸻
PHASE 4 — ROOT CAUSE (MANDATORY)

Explicitly answer:
	1.	Which SVG elements are paintable?
	2.	Which elements are currently being animated?
	3.	Why the animation is invisible despite CSS existing?
	4.	Which exact rule must change?

⸻

PHASE 5 — FIX IMPLEMENTATION

Implement fixes so that:
	•	Edges animate by targeting <path>
	•	Nodes animate by targeting:
	•	<rect> for containers
	•	<text> for labels
	•	Group-level intent is mapped to child primitives

Example:
	•	Animation plan targets ent0003
	•	Executor maps ent0003 → rect + text children

    PHASE 6 — HARD TEST CASES (ALL MUST PASS)
	1.	Node pulse test:
	•	Rect scales or glows visibly.
	2.	Edge flow test:
	•	Path dashoffset visibly animates.
	3.	React re-render test:
	•	Toggle animation ON/OFF repeatedly.
	4.	Regression:
	•	Removing animation code restores original SVG.

⸻

PASSING CRITERIA (NON-NEGOTIABLE)
	•	At least one node visibly animates.
	•	At least one edge visibly animates.
	•	Animation survives re-render.
	•	DOM inspection confirms animated primitives.

    FAILURE RULE

If animation is not visible in the browser:
	•	The task is NOT complete.
	•	Return to Phase 2.

DO NOT assume correctness.
Only visible motion counts.

---

## Final, blunt truth (important)

> Your system is not failing because SVG animation is hard.  
> It’s failing because you are animating **containers**, not **paint**.

Once Codex is forced to discover that in the browser, the fix becomes obvious and permanent.

If you want, next I can:
- Design a **primitive-mapping layer** (`ent → rect+text`)
- Help you formalize **SVG animation semantics**
- Add a **canary animation** that must always move
- Convert this into a **CI visual test**

Just tell me the next step.