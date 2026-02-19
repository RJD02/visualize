A) INVESTIGATION: PROVE HOW SVG IS RENDERED
	1.	Search the UI code for all places where diagram output is rendered.
Grep for: <img, dangerouslySetInnerHTML, <object, <embed, iframe, innerHTML, svgString, diagram, renderSvg, svg, plantuml, mermaid.
Identify the component(s) that render the final diagram.
	2.	Identify the runtime DOM structure for a rendered diagram.
Add a temporary data-testid to the diagram container (for example: data-testid=“diagram-root”).
Add a minimal debug flag (DEBUG_SVG_RENDER=true) that logs:

	•	rendering mode: “img” | “object” | “inline”
	•	tagName of the diagram root child
	•	whether an  exists as a descendant

This must be behind a debug flag so it does not pollute production logs.
	3.	Add Cypress E2E checks (must run headless) that:

	•	Generate any diagram
	•	Assert exactly one of these is true:
	•	INLINE MODE: container contains a real  element in DOM
	•	IMG/OBJECT MODE: container contains  or / with src/data pointing to svg/png
	•	Log diagramRenderMode=INLINE or diagramRenderMode=IMG in test output

The test must fail if both modes appear or neither appears.

============================================================
B) CONDITIONAL FEATURE: FONT AWESOME SUPPORT

If and only if Cypress and code inspection confirm diagram is INLINE SVG in DOM:
Implement Font Awesome support for diagram node icons.

If diagram is IMG/OBJECT/EMBED:
	•	Do NOT implement Font Awesome for diagram nodes
	•	Add a dev-mode UI warning: “Font Awesome icons not supported in IMG-based SVG rendering.”
	•	Add a clear TODO comment recommending SVG symbol/use injection instead of HTML-based icons.

============================================================
C) IMPLEMENTATION (INLINE MODE ONLY)

Goal:
Allow the styling agent to request Font Awesome icons and have them appear inside diagram nodes, including animated SVG. This must work inside the chat-driven rendering pipeline and must not break animation.

Important constraints:
	•	Do not insert HTML  tags directly inside SVG (unless using foreignObject).
	•	Prefer deterministic SVG symbol injection instead of runtime font replacement.
	•	Styling must be controlled via an allow-list.

Preferred Implementation Strategy (SVG symbol injection):
	1.	Add Font Awesome SVG dependency strategy:
Use Font Awesome SVG packages locally (preferred), or download required SVG path data and store locally. Do not rely on runtime network resolution for export stability.
	2.	Create an icon registry in the UI layer:
Example structure:
iconRegistry = {
database: { viewBox: “0 0 512 512”, path: “…” },
shield: { viewBox: “…”, path: “…” }
}

Only allow icons from this registry.
	3.	Extend IR or style spec to support icons per node:
Example conceptual structure:
node_style.icon = {
key: “database”,
position: “left”,
size: 18,
color: “#hex”
}

Styling agent must only output icon keys from the allow-list.
	4.	Post-process generated SVG string:

	•	Parse SVG using DOMParser
	•	Ensure  exists
	•	Inject 
	•	For each node group, insert:

	•	Shift label text so icon and text do not overlap
	•	Add CSS class .node-icon with proper fill and transition rules

	5.	Ensure icons animate correctly:
Icons must be inside the same node group that receives animation classes so they inherit animation behavior automatically.

============================================================
D) OPTIONAL FALLBACK (IF YOU INSIST ON CDN)

If using CDN:
	•	Add Font Awesome CSS CDN to root layout
	•	Keep it behind feature flag ENABLE_FA_CDN
	•	If injecting icons into SVG, use foreignObject:
Insert foreignObject inside node group
Inside foreignObject render XHTML div and 

Be aware:
	•	foreignObject may not export cleanly to PNG/GIF
	•	Must add Cypress test to confirm rendering works

============================================================
E) STYLING AGENT INTEGRATION

Update styling agent to:
	•	Accept IR or IR + user edit
	•	Decide icon usage semantically
	•	Output structured patch operations like:
op: “set_node_icon”
node_id: “…”
icon_key: “database”
size: 18
position: “left”

Validate icon_key against allow-list before applying.

Add audit log:
Store icon decisions in styling audit trail.

============================================================
F) CYPRESS TESTS (MANDATORY)

Test 1: Render Mode Detection
Generate diagram.
Assert exactly one rendering mode.
Log mode clearly.

Test 2: Icon Injection (INLINE mode only)
Prompt: “Use database icon for Postgres and shield icon for Vault.”
Assert:
	•	 exists
	•	 exists inside correct node group
	•	Icon is visible (opacity > 0, width > 0)

Test 3: Animation + Icons
Generate diagram.
Request animation.
Assert:
	•	Node group has animation class
	•	Icon exists inside animated node group
	•	Screenshot before and during animation shows icon present

Test 4: Invalid Icon Handling
Prompt invalid icon.
Assert:
	•	No crash
	•	Fallback icon or graceful rejection
	•	Error message shown in chat

============================================================
SUCCESS CRITERIA
	•	Rendering mode is proven and logged.
	•	Font Awesome support works only in INLINE mode.
	•	Icons animate with nodes.
	•	No breakage in GIF export (if applicable).
	•	All Cypress tests pass headless on remote server.
	•	No overlays used; everything renders in chat window.

Proceed in strict order:
	1.	Prove rendering mode.
	2.	Implement only correct branch.
	3.	Add tests.
	4.	Confirm headless success.
	5.	Remove debug instrumentation before completion.