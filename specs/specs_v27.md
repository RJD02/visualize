You are a senior AI systems engineer enhancing styling support for diagram generation.

Context:
- Users can generate diagrams from text, repos, docs, or previous SVGs.
- Mermaid and PlantUML are already integrated and produce neutral SVG.
- Users want to request styles at any time — either before the SVG is generated (pre-SVG) or after it exists (post-SVG).
- Styling requests include colors, emphasis, highlights, typography, block level styling, edge styling and animation aesthetics.
- Mermaid styling must use CSS-compatible hex values and valid Mermaid syntax (`classDef`, `style`, `themeVariables`) because Mermaid only accepts hex colors and specific syntax.  [oai_citation:2‡mermaid.js.org](https://mermaid.js.org/config/theming.html?utm_source=chatgpt.com)
- PlantUML styling must use `skinparam`, `<style>` blocks, and valid PlantUML syntax.  [oai_citation:3‡PlantUML.com](https://plantuml.com/style?utm_source=chatgpt.com)

Goal:
Add full support to interpret user styling requests from the chat window and transform them into valid diagram styles at both pre-SVG diagram generation and post-SVG modification.

This must be implemented as a dedicated **Styling Agent** tool available to the chat assistant.

---

FEATURE REQUIREMENTS

1. **Styling Agent Registration**
   - Register a new MCP/ADK tool:
     `svg_styling_agent`
   - Responsibility:
     * Accept: SVG text (or diagram input + target engine)
     * Accept: Styling Intent
     * Produce: Updated SVG or renderer syntax with styling applied

2. **Styling Intent Extraction**
   - When the user asks things like:
     - “Use orange and yellow blocks”
     - “Make edges blue and thicker”
     - “Highlight database in red before animation”
     - “Use pastel theme for this diagram”
   - Extract structured styling intent into:
     ```
     {
       "blockColors": { "primary": "#FFA500", "secondary":"#FFFF00" },
       "textStyle": { "fontWeight":"bold", "fontColor":"#333333" },
       "edgeStyle": { "strokeColor":"#0000FF", "strokeWidth":"2px" },
       "theme": "pastel"
     }
     ```

3. **Pre-SVG Styling Integration**
   - For new diagram requests:
     - Translate styling intent into valid renderer syntax
     - For Mermaid:
       * Use `classDef`/`style` or `%%{init: { themeVariables: {...} }}%%` blocks to apply colors and fonts, respecting hex color requirements.  [oai_citation:4‡mermaid.js.org](https://mermaid.js.org/config/theming.html?utm_source=chatgpt.com)
     - For PlantUML:
       * Use `skinparam`, `<style>` sections and element selectors to apply provided styles.  [oai_citation:5‡PlantUML.com](https://plantuml.com/style?utm_source=chatgpt.com)

4. **Post-SVG Styling Transformation**
   - For existing SVGs:
     - Parse the SVG structure
     - Apply the intent as:
       * Inline styles on SVG elements (e.g., `<rect fill="#FFA500">`)
       * Scoped `<style>` blocks injected at the top of the SVG
     - Do not alter structure or animation logic

5. **Fallback & Clarification**
   - If a user request is ambiguous (e.g., “make it more vibrant”), ask a clarifying question only if strictly necessary.
   - Otherwise assume best defaults based on context.

6. **Aesthetic Mapping Rules**
   - Provide mapping from intent to styles such as:
     * “highlight X” → thicker stroke, contrasting color
     * “calm” → pastel palette
     * “attention” → bolder fill colors + bold text
   - Use a palette lookup when colors are described verbally.

---

TEST CASES (AUTOMATED VERIFICATION)

### Test 1 — Simple Color Request
Input:
“Generate a flowchart with orange and yellow blocks.”
Expect:
- Generated Mermaid code includes `classDef` or `style` for orange/yellow appropriately.  [oai_citation:6‡Stack Overflow](https://stackoverflow.com/questions/74894540/mermaid-js-flow-chart-full-list-of-available-options-to-style-a-node?utm_source=chatgpt.com)
- SVG reflects the colors.

### Test 2 — Post-SVG Text Styling
Given:
Existing SVG
Request:
“Make all labels bold and dark grey.”
Expect:
- All `<text>` elements have `font-weight: bold` and `fill: #444444`.

### Test 3 — Edge Styling Request
Input:
“Make edges thick and blue.”
Expect:
- Edges in Mermaid/PlantUML code include stroke width 2px+ and stroke color blue.
- Updated SVG matches that.

### Test 4 — Ambiguous Palette
Input:
“Use a pastel theme.”
Expect:
- The agent chooses a valid pastel palette and applies it consistently.

### Test 5 — Compound Request
Input:
“Create a sequence diagram with green blocks and light text.”
Expect:
- Mermaid/PlantUML code includes both block color and text color rules.

---

SUCCESS CRITERIA (ALL MUST PASS)

- User styling requests produce visible, correct styling in SVG.
- Pre-SVG integration and post-SVG transformation are both supported.
- Agent only injects valid Mermaid/PlantUML style syntax.
- SVG structure and animation remain unchanged.
- Clarification questions are asked only when intent is ambiguous.
- Automated test cases pass before manual UI testing.

---

IMPORTANT PHILOSOPHY

Styling is BOTH:
- a **diagram generation concern** (when requested upfront), and
- a **post-SVG transformation concern** (when applied later).

Both must be handled by a unified **Styling Agent** that interprets chat intent and applies valid styles without altering structure or semantic meaning.

This prompt ensures high-quality styling support in your chat UI.