You are refactoring an Architecture Visualization system.

CURRENT PROBLEM:
The system uses SVG (or SVG-like layout instructions) as an Intermediate Representation (IR).
This tightly couples meaning to pixels, makes animation hard, and prevents deterministic,
semantic evolution of diagrams.

SVG MUST NOT be used as IR.

SVG / PNG / Canvas are RENDER OUTPUTS only.

---

## CORE GOAL (NON-NEGOTIABLE)

Replace SVG-as-IR with a new **Semantic Architecture IR** that is:

- More readable than UML
- More semantic than SVG
- Deterministically convertible to UML
- Stable under small changes (small IR diff → small diagram diff)
- Animation-ready (time-aware, but no animation yet)

Final output (for now) MUST be a PlantUML-generated image.

---

## TARGET PIPELINE (MANDATORY)

Input (text / repo / code)
        ↓
Semantic Architecture IR   ← YOU MUST DESIGN THIS
        ↓
Deterministic IR → UML Compiler
        ↓
UML AST (internal)
        ↓
PlantUML
        ↓
FINAL IMAGE

IR MUST NEVER CONTAIN SVG, COORDINATES, OR LAYOUT DATA.

---

## SEMANTIC IR DESIGN REQUIREMENTS

### 1. IR MUST MODEL INTENT, NOT VISUALS

The IR must describe:
- Actors
- Systems
- Containers
- Components
- Interfaces (logical)
- Relationships
- Direction
- Optional interaction order / phase

The IR must NOT include:
- x/y coordinates
- width/height
- colors
- arrows, boxes, pixels
- PlantUML syntax

---

### 2. IR MUST BE MORE READABLE THAN UML

The IR should be:
- Line-oriented or structured (YAML/JSON-like)
- Easy for humans to read and edit
- Explicit and boring (no magic inference)

Example style (illustrative only, you must design properly):


This is NOT UML.
This is a **semantic description that compiles to UML**.

---

### 3. IR → UML MUST BE STRICTLY DETERMINISTIC

You MUST ensure:

- Same IR → same UML AST → same PlantUML
- Ordering is canonical and stable
- No implicit relationships
- No auto-layout logic in IR
- No LLM creativity in structure

Small IR change MUST result in:
- Small UML AST change
- Small PlantUML diff
- Small visual change in final image

This property is CRITICAL.

---

### 4. UML IS A COMPILATION TARGET, NOT THE SOURCE

- UML concepts (actor, component, dependency, message) are targets
- IR concepts may be simpler or flatter
- UML verbosity must NOT leak into IR

Think of UML as assembly code.
Think of IR as high-level source code.

---

### 5. SEQUENCE DIAGRAM READINESS (NO ANIMATION YET)

IR must support ordered interactions, such as:

- step / phase / order
- synchronous vs async
- request vs response

This allows:
- IR → UML Sequence Diagram
- IR → animation later

Do NOT implement animation.
Only ensure IR does not need redesign later.

---

## IMPLEMENTATION REQUIREMENTS

1. Delete SVG-as-IR completely
2. Introduce a new Semantic IR module
3. Write a deterministic IR → UML compiler
4. PlantUML must be generated ONLY from the UML AST
5. IR must never leak to the user by default

---

## TEST CASES (MANDATORY)

### Test 1: Small Change Stability
Change one relationship in IR  
Expected:
- Only that edge changes in UML
- Diagram remains otherwise identical

FAIL if layout or unrelated edges change.

---

### Test 2: Deterministic Ordering
Reorder IR declarations  
Expected:
- UML and PlantUML output unchanged

FAIL if order affects output.

---

### Test 3: No Visual Leakage
Inspect IR  
Expected:
- No SVG, coordinates, arrows, or layout hints

FAIL if visual concepts exist.

---

### Test 4: Sequence Diagram Capability
Add ordered interactions to IR  
Expected:
- Valid UML sequence diagram generated

FAIL if interaction modeling is impossible.

---

### Test 5: IR Readability Check
A human should be able to:
- Read IR
- Understand architecture
- Predict diagram shape

FAIL if IR is as complex as UML.

---

## ELIGIBILITY CRITERIA (DEFINITION OF DONE)

This refactor is COMPLETE only if:

- SVG is fully removed as IR
- IR is semantic, readable, and stable
- IR → UML is deterministic and compiler-driven
- Small IR diffs produce small diagram diffs
- Final output is a PlantUML-generated image

If IR resembles SVG, PlantUML, or layout instructions,
THE TASK IS FAILED.

Proceed with the refactor.
