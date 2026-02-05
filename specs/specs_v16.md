You are refactoring an Architecture Visualization system.

CURRENT STATE (PROBLEM):
The system’s Intermediate Representation (IR) is too close to visual/layout formats (SVG-like thinking). This makes it hard to scale toward:
- UML generation
- Multiple UML diagram types
- Future animation (time-based transitions)

We must move IR ABOVE UML, not below it.

SVG / PlantUML / Mermaid are RENDER TARGETS — not the IR.

---

## CORE ARCHITECTURAL DECISION (NON-NEGOTIABLE)

The new IR must be:

- Semantic
- UML-compatible
- Renderer-agnostic
- Animation-ready
- Deterministic

The final output (for now) MUST be a **PlantUML-generated IMAGE**.

---

## TARGET PIPELINE (MANDATORY)

Input (text / repo / code)
        ↓
Semantic IR (UML-SUPERSET)   ← YOU ARE BUILDING THIS
        ↓
UML Adapter
        ↓
PlantUML
        ↓
FINAL IMAGE (PNG / SVG)

NO SVG, CANVAS, OR PIXEL THINKING IN IR.

---

## NEW IR DESIGN RULES

### 1. IR MUST MODEL CONCEPTS, NOT SHAPES

IR should represent:

- Systems
- Containers
- Components
- Actors
- Interfaces
- Relationships
- Directionality
- Ownership
- Optional runtime semantics

IR MUST NOT include:
- Coordinates
- Width / height
- Colors (except abstract style tags)
- Layout positioning

---

### 2. IR MUST MAP CLEANLY TO UML

Every IR construct must have a **clear UML meaning**.

Examples:

- System → UML Package / Boundary
- Container → UML Component
- Actor → UML Actor
- Relationship → UML Dependency / Association
- Runtime call → UML Sequence Message (future)

If something cannot be expressed in UML terms, it does NOT belong in IR.

---

### 3. IR MUST SUPPORT MULTIPLE UML DIAGRAM TYPES

The same IR must be able to generate:

- C4 Context Diagram
- C4 Container Diagram
- Component Diagram
- Sequence Diagram (future)
- Activity Diagram (future)

This means:
- Diagram type is a VIEW over IR
- IR does NOT change per diagram type

---

### 4. ANIMATION-READINESS (IMPORTANT)

IR must be capable of supporting animation WITHOUT redesign.

Therefore:
- Relationships may optionally include:
  - phase
  - step
  - order
  - lifecycle
- Components may have:
  - state
  - activation
  - visibility

This enables:
- IR → UML Sequence Diagram
- IR → Animated SVG / GIF / MP4 (later)

NO animation is implemented now — only capability.

---

## PLANTUML OUTPUT REQUIREMENTS (CURRENT PHASE)

- PlantUML is the ONLY renderer for now
- Output must be:
  - A valid PlantUML diagram
  - Rendered to an IMAGE
- Image MUST include:
  - Diagram title (e.g. “System Architecture Diagram”)
  - Clear boundaries and labels

IR must never leak into the user output.

---

## TEST CASES (MANDATORY)

### Test 1: UML Semantic Integrity
**Input:** Architecture description  
**Expected:**
- IR elements map cleanly to UML constructs
- No visual/layout data exists in IR

FAIL if IR contains SVG/layout concepts.

---

### Test 2: IR → PlantUML Determinism
**Input:** Same architecture twice  
**Expected:**
- Generated PlantUML is semantically identical
- Final images are identical

FAIL if output differs.

---

### Test 3: Diagram View Switching
**Input:** Same IR, request different diagram types  
**Expected:**
- Context diagram and Container diagram generated from SAME IR

FAIL if IR must be regenerated per diagram.

---

### Test 4: No IR Leakage
**Input:** Normal user request  
**Expected:**
- Only PlantUML-generated image is shown
- IR is completely hidden

FAIL if IR appears in chat.

---

### Test 5: Animation Capability Check (Structural)
**Input:** IR inspection (internal only)  
**Expected:**
- IR supports ordering / phase metadata
- No rendering logic embedded

FAIL if animation would require IR redesign.

---

## ELIGIBILITY CRITERIA (DEFINITION OF DONE)

This task is COMPLETE only if:

- IR is UML-semantic, not visual
- PlantUML image is the final user-facing artifact
- IR can support future animation WITHOUT structural change
- All tests above pass

If IR resembles SVG, layout JSON, or canvas instructions,
THE TASK IS FAILED.

Proceed with the refactor.