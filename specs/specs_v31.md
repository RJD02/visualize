You are a senior QA + systems engineer.

Your task is to add an automated Cypress-based UI testing agent that verifies
whether user-requested diagram styling (colors) is actually rendered in the UI.

This agent must be able to:
	•	Open the running UI
	•	Submit a chat prompt
	•	Wait for diagram generation
	•	Inspect the rendered SVG
	•	Assert that requested colors are present
	•	Produce a clear failure report if not

This test will be used by Codex itself to debug styling issues.

⸻

TEST SCENARIO (MANDATORY)

User Prompt (exact text):

“””
https://github.com/RJD02/job-portal-go
Can you generate a diagram with orange and blue blocks, for this GitHub repo
“””

Expected Result:
	•	A diagram is generated
	•	The diagram is rendered as inline SVG (not )
	•	Diagram blocks contain orange and blue colors
	•	Either as fill or stroke
	•	Either inline or via SVG <style>

⸻

TASKS

1. Add Cypress Test Infrastructure

If not present:
	•	Install Cypress
	•	Add cypress.config.*
	•	Ensure Cypress can run against the local UI (e.g. http://localhost:3000)

⸻

2. Create Cypress Test: diagram-styling.cy.ts

The test must:
	1.	Open the UI
	2.	Enter the user prompt into the chat input
	3.	Submit the prompt
	4.	Wait for the diagram to appear
	5.	Locate the rendered SVG
	6.	Assert color presence

⸻

3. SVG Selection Rules (CRITICAL)

The test must FAIL if:
	•	The diagram is rendered as <img>
	•	No <svg> is present in the DOM

Selector example:

“””
cy.get(‘svg’).should(‘exist’)
cy.get(‘img’).should(‘not.exist’)
“””

⸻

4. Color Assertion Rules

The test must search the SVG for orange and blue, allowing flexibility.

Accepted values include:

Orange:
	•	#FFA500
	•	#ff9800
	•	rgb(255, 165, 0)

Blue:
	•	#0000FF
	•	#2196f3
	•	rgb(33, 150, 243)

Check:
	•	fill
	•	stroke
	•	styles inside <style> blocks

Example logic:

“””
cy.get(‘svg’).then($svg => {
const svgText = $svg[0].outerHTML

const hasOrange = /#FFA500|#ff9800|rgb\(255,\\s*165,\\s*0\\)/i.test(svgText)
const hasBlue   = /#0000FF|#2196f3|rgb\(33,\\s*150,\\s*243\\)/i.test(svgText)

expect(hasOrange, ‘orange color present’).to.be.true
expect(hasBlue, ‘blue color present’).to.be.true
})
“””

⸻

5. Diagnostic Failure Report (MANDATORY)

If the test fails, output a clear diagnostic report that includes:
	•	Whether SVG was inline or <img>
	•	Whether any <style> block existed inside SVG
	•	Which colors were found (if any)
	•	A truncated SVG snippet (first 500 characters)

Example failure output:

“””
❌ Diagram styling verification failed
	•	SVG inline: YES
	•	 detected: NO
    <style> in SVG: YES
	•	Found colors: #000000, #FFFFFF
	•	Missing requested colors: ORANGE, BLUE

SVG snippet:
  <style>...</style>


This report must be logged clearly so Codex can reason about the failure.

⸻

6. Codex Self-Debug Loop (IMPORTANT)

Add a comment or hook so that if this test fails, Codex should:
	1.	Inspect the failure report
	2.	Determine which layer failed:
	•	Styling intent extraction
	•	Styling agent plan
	•	SVG embedding
	•	Inline SVG rendering
	3.	Propose a fix
	4.	Re-run the test

⸻

TEST PASS CRITERIA

ALL must be true:
	•	Cypress test passes
	•	SVG is inline
	•	Orange and blue colors are detected in SVG
	•	Diagram visually reflects the requested colors
	•	No manual inspection required

⸻

PHILOSOPHY (DO NOT IGNORE)

If the UI visually looks correct but the test fails,
the system is not deterministic.

If the test passes but the UI looks wrong,
the rendering pipeline is broken.

This Cypress agent is the source of truth.
“””