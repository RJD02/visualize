You are working on an Architecture Diagram Generator system.

CURRENT PROBLEM:
The system currently leaks intermediate representations (IR) or produces ambiguous “image + text hybrids” that users do not recognize. The final output must ALWAYS be a clear, self-contained IMAGE that represents the architecture. IR may exist internally but must NEVER be exposed to the user unless explicitly requested.

CORE PRINCIPLE (NON-NEGOTIABLE):
IR is an internal compiler-like representation.
IMAGE is the final product.

The correct pipeline is:

Input (text / repo / code)
        ↓
Intermediate Representation (IR) [INTERNAL ONLY]
        ↓
Renderer Adapter (PlantUML / Mermaid / SVG / Canvas)
        ↓
FINAL IMAGE (PNG / SVG)

The user should only see the final image.

---

## REQUIRED CHANGES

### 1. Enforce Image-Only Output
- The system must ALWAYS return an image as the final output.
- No raw IR, partial IR, or structural text should appear in chat.
- If IR is generated, it must remain internal.

### 2. Explicit Diagram Typing
Every generated image MUST clearly identify itself as one of:
- "System Architecture Diagram"
- "C4 Context Diagram"
- "C4 Container Diagram"
- "Runtime Flow Diagram"
- "Repo Architecture Diagram"

This can be done via:
- A title rendered into the image
- Or metadata passed to the renderer

This is to avoid user confusion.

### 3. IR Rules
- IR must be deterministic, structured, and renderer-agnostic.
- IR MUST NOT resemble PlantUML or Mermaid syntax.
- IR should describe:
  - Components
  - Lanes / layers
  - Relationships
  - Direction
  - Optional styling hints (theme, layout)
- IR is never shown to the user by default.

### 4. Renderer Abstraction
- Rendering must happen via adapters:
  - IR → PlantUML → Image
  - IR → Mermaid → Image
  - IR → SVG → Image
- The renderer must be swappable without changing IR.

### 5. Final Output Contract
The final system response must contain:
- Exactly one image (or multiple images only if explicitly requested)
- No explanatory IR text
- No “image cum text” hybrids

---

## TEST CASES (MUST BE IMPLEMENTED)

### Test Case 1: Image-Only Guarantee
**Input:** Architecture description text  
**Expected Result:**  
- Output contains only an image
- No IR, JSON, YAML, or structural text is visible

FAIL if any IR-like text appears.

---

### Test Case 2: Deterministic Regeneration
**Input:** Same architecture input twice  
**Expected Result:**  
- Generated images are identical (byte-level or semantic equivalence)

FAIL if images differ structurally.

---

### Test Case 3: Renderer Swap Safety
**Input:** Same IR rendered via PlantUML and Mermaid  
**Expected Result:**  
- Both outputs are valid images
- Both represent the same architecture semantics

FAIL if IR changes per renderer.

---

### Test Case 4: Diagram Type Labeling
**Input:** Repo structure input  
**Expected Result:**  
- Final image clearly labels itself (e.g., "Repo Architecture Diagram")

FAIL if the image is unlabeled or ambiguous.

---

### Test Case 5: No IR Leakage
**Input:** Any standard request  
**Expected Result:**  
- User-visible output contains no internal representation
- IR only appears if user explicitly asks “show IR”

FAIL if IR is exposed by default.

---

### Test Case 6: Multi-Image Control
**Input:** User requests N diagrams  
**Expected Result:**  
- Exactly N images are rendered and shown
- No more, no fewer

FAIL if image count does not match request.

---

## ELIGIBILITY CRITERIA (DEFINITION OF DONE)

This task is considered COMPLETE only if:
- All tests above pass
- IR is fully internalized
- The final user experience produces unmistakable, standalone images
- The output feels like a finished diagram, not an intermediate artifact

If any ambiguity remains in user perception, the task is NOT complete.

Proceed to repair the system accordingly.