You are a senior systems engineer tasked with fixing a styling & rendering bug in the diagram generation pipeline.

### BACKGROUND
- Diagram SVGs are currently rendered via `<img src="...">`.
- User style requests like “vibrant colours” are not being applied because:
   * CSS in overlays does not penetrate `<img>` SVG internals
   * SVGs are neutral and then styled externally, which doesn’t work
- Animation specs are also injected externally and do not affect the rendered image.
- The UI should not try to style `<img>` elements — it must render fully styled SVGs.

### GOAL
Fix the codebase so that:
1. **All user-requested styling is applied inside the SVG markup itself** (pre-render or post-SVG transformation), including:
   - Block colours
   - Text colours
   - Edge colours
   - Animation style definitions
2. **The SVG is inlined or embedded with its styles**, not rendered as a bare `<img>`.
3. **The UI only needs to render the given SVG** — no external CSS or overlay hacks should be required.
4. **Animation specs must be included in the SVG**, so that when the SVG is rendered, both colour styling and animation are visible in one artifact.

### REQUIRED CHANGES

#### 1) Inline SVG Rendering
- Replace current usage of:
  ```html
  <img src="diagram.svg" />
   ```

with:

<div class="diagram-container">
  <!-- Inline SVG text here -->
</div>

	•	The backend or client must fetch the SVG as text and embed it as inline SVG markup.

2) Embed Styles & Animation Inside SVG
	•	The Styling Agent and Animation Agent must emit <style> blocks inside the SVG itself.
	•	This includes:
	•	Colour rules requested by the user
	•	Animation keyframes and selectors
	•	Any text or block emphasis styles

Example inside SVG:

<svg ...>
  <style>
    /* User requested colours */
    .block-primary { fill: #FFA500; stroke: #000000; }
    .block-secondary { fill: #FFFF00; stroke: #000000; }
    /* Animation keyframes */
    @keyframes pulse { ... }
    .animate-primary { animation: pulse 1s infinite; }
  </style>
  <!-- Diagram content -->
</svg>

3) Styling Agent Update
	•	The Styling Agent must:
	•	Generate styles in terms of SVG classes and selectors
	•	Insert the styles into a <style> block inside the SVG
	•	Not rely on external CSS files or overlays

4) Animation Agent Update
	•	The Animation Agent must:
	•	Embed animation rules inside the SVG
	•	Use inline <style> or SVG animation tags (<animate>, <animateMotion>, etc.)
	•	Ensure animation does not depend on external CSS

5) UI Changes
	•	The UI renderer must:
	•	Load the SVG as text
	•	Insert it directly into the DOM as inline SVG
	•	Not wrap it in <img> or block external style overlays

6) Fallback & Backwards Compatibility
	•	Detect if SVG is not inlined and convert it automatically
	•	Warn the user if inline rendering is not possible

TEST CASES (AUTOMATED)

Test 1 — Styling in SVG
User:
“Generate a diagram with vibrant colours”
Expect:
	•	SVG contains a <style> block with colour rules
	•	Blocks/text are coloured per request
	•	UI renders the colours correctly

Test 2 — Animation in SVG
User:
“Animate and highlight API calls”
Expect:
	•	SVG contains animation keyframes inside <style>
	•	Animated elements animate without external CSS

Test 3 — Combined Styling + Animation
User:
“Make nodes orange and pulse”
Expect:
	•	SVG contains inline styles + animation for nodes
	•	UI shows both effects with a single SVG

Test 4 — Regression
	•	Removing style request
Expect:
	•	SVG output remains neutral
	•	Inline SVG still renders cleanly

Test 5 — Inline Rendering
	•	Confirm no <img> remains for core diagrams
Expect:
	•	All diagrams are inline SVG
	•	UI must not render <img> for styled diagrams

SUCCESS CRITERIA
	•	User requests for colours are reflected inside SVG markup
	•	Animation specs are inside SVG and functional
	•	UI does NOT require external CSS for diagram styling
	•	Styles and animations are deterministic and auditable
	•	Tests pass automatically

IMPORTANT RULES
	•	Do NOT rely on external <style> blocks targeting <img>
	•	Do NOT mutate DOM after render to style SVG
	•	All styling decisions must be embedded inside the SVG itself

Your output should modify the codebase so that:
	•	Prescribed styling becomes part of each diagram artifact
	•	The UI simply renders the SVG
	•	No external overlays are necessary
   By inlining the SVG and embedding styles inside it, you guarantee:

✅ Colours show up
✅ Animations show up
✅ User style requests are honored
✅ No overlay CSS hacks needed