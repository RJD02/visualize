You are a senior frontend rendering engineer. Your task is to PROVE whether SVG icon embedding inside generated diagrams works in this application.

Do not assume it works.
Do not assume it fails.
You must verify it end-to-end using deterministic rendering and Cypress headless tests.

The goal is binary:

Either:
	1.	Icon embedding works reliably (symbol + use or foreignObject), or
	2.	It does NOT work, and we must abandon this approach.

============================================================
PHASE 1 — DETERMINE RENDERING MODE
	1.	Inspect how diagrams are rendered in the UI.
	•	Search for , , , iframe, dangerouslySetInnerHTML.
	•	Log the render mode under a debug flag:
window.DEBUG_SVG_RENDER = true
	•	Print:
	•	root container tag
	•	first child tag
	•	whether inline  exists
	•	whether it is embedded via img src
	2.	Add Cypress test:
	•	Visit app
	•	Generate deterministic diagram
	•	Assert one of:
INLINE MODE → container contains actual 
IMG MODE → container contains 

If IMG mode:
Immediately stop icon injection test.
Print:
“ICON EMBEDDING NOT POSSIBLE: SVG RENDERED VIA IMG”
Exit test successfully (expected behavior).

If INLINE mode:
Proceed to Phase 2.

============================================================
PHASE 2 — MINIMAL ICON INJECTION TEST (NO AGENT)

Do NOT rely on styling agent.
Hard-code injection for test.
	1.	Create a deterministic test route:
/__test/icon-injection
This route:
	•	Renders a minimal inline SVG:


Test Node
	2.	Modify it to inject:
<defs>
  <symbol id="test-icon" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" fill="red"/>
  </symbol>
</defs>

Inside SVG:


	3.	Ensure SVG is inline in DOM.
	4.	Add Cypress test:
	•	Visit /__test/icon-injection
	•	Assert:
cy.get(‘svg’).should(‘exist’)
cy.get(‘symbol#test-icon’).should(‘exist’)
cy.get(‘use[href=”#test-icon”]’).should(‘exist’)
	•	Then assert bounding box:
getBoundingClientRect().width > 0
getComputedStyle(…).display !== “none”
opacity !== “0”

If this fails:
Log:
“INLINE SVG SYMBOL INJECTION FAILED”
Stop.

If this passes:
Proceed to Phase 3.

============================================================
PHASE 3 — APPLY ICON TO REAL DIAGRAM NODE

Now test against real diagram output.
	1.	Generate deterministic diagram with a known node (e.g. Postgres).
	2.	Manually inject a simple circle symbol into that node group.
Do not use Font Awesome yet.
Just inject a red circle.
	3.	Cypress test:
	•	Assert:
SVG contains symbol
Node group contains 
Icon is visible (bounding box non-zero)
	4.	Take screenshot before and after injection.

If visible:
Icon embedding WORKS.
Proceed to Phase 4.

If not visible:
Investigate:
- ViewBox mismatch
- CSS fill override
- Overflow hidden
- transform issues
- animation hiding icon

Fix and re-test.

============================================================
PHASE 4 — TEST WITH FONT AWESOME SVG PATH

Replace test circle with actual FA path:

   <symbol id="fa-test" viewBox="0 0 512 512">
     <path d="..." />
   </symbol>
Inject via .

Cypress must verify:
	•	symbol exists
	•	use exists
	•	visible bounding box
	•	no console errors

============================================================
PHASE 5 — TEST DURING ANIMATION
	1.	Trigger animation mode.
	2.	Ensure node group gets animation class.
	3.	Assert icon remains visible during animation.

Cypress:
	•	Check DOM after 500ms.
	•	Confirm  still exists.
	•	Confirm opacity > 0.

============================================================
FINAL DECISION LOGIC

If all tests pass:
Log:
“ICON EMBEDDING CONFIRMED — SAFE TO PROCEED”
Return success.

If any test fails:
Log precise failure:
- “FAILURE: INLINE RENDERING NOT DETECTED”
- “FAILURE: SYMBOL INJECTION NOT WORKING”
- “FAILURE: ICON HIDDEN BY CSS”
- etc.

Do NOT guess.
Provide exact failure reason.

============================================================
SUCCESS CRITERIA

We must have deterministic proof that:
	1.	Inline SVG rendering exists.
	2.	Symbol injection works.
	3.	 renders visibly.
	4.	Works with animation.
	5.	Works headless in Cypress.

If not, conclude icon embedding is not viable and recommend alternate architecture (e.g., raster overlay, canvas layer, or external HTML layer).

Proceed step-by-step.
Do not skip phases.
Do not rely on agent pipeline.
Prove embedding works independently first./