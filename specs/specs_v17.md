You are implementing a deterministic compiler-style pipeline that converts
a Semantic Architecture IR into UML (PlantUML), using an LLM ONLY as a constrained
transformation step.

THIS IS NOT FREE-FORM TEXT GENERATION.

The LLM must behave like a compiler pass, not a creative writer.

---

## CORE ARCHITECTURE (NON-NEGOTIABLE)

The pipeline MUST be:

Semantic IR (structured, deterministic)
        ↓
LLM (STRICTLY CONSTRAINED, SCHEMA-BOUND)
        ↓
UML AST (internal)
        ↓
PlantUML code
        ↓
FINAL IMAGE

LLM output MUST NOT go directly to the user.
LLM output MUST be validated, normalized, and compiled by code.

---

## KEY PRINCIPLE

> Determinism is enforced by CODE, not by prompting alone.

The LLM is a helper that:
- Expands semantics
- Applies naming conventions
- Resolves UML mapping choices

The CODE is responsible for:
- Validation
- Ordering
- Canonicalization
- Optimization
- Emission

---

## SEMANTIC IR REQUIREMENTS

The IR is:
- Renderer-agnostic
- UML-compatible
- Animation-ready
- Layout-free

IR contains:
- Actors
- Systems
- Containers
- Components
- Relationships
- Direction
- Optional phase/order metadata

IR MUST NOT contain:
- Coordinates
- Visual layout
- PlantUML syntax
- SVG concepts

---

## LLM ROLE (STRICTLY LIMITED)

The LLM may ONLY:
1. Map IR elements to UML concepts
2. Expand implicit relationships
3. Normalize naming
4. Choose UML relationship types where ambiguous

The LLM MUST NOT:
- Invent new components
- Invent new relationships
- Change IR structure
- Output raw PlantUML directly

LLM output MUST be a STRUCTURED UML AST (JSON or equivalent).

---

## UML AST (INTERNAL)

Define an internal UML AST representation, for example:
- packages
- actors
- components
- dependencies
- sequences (future)

This AST is:
- Deterministic
- Orderable
- Diffable
- Testable

The UML AST is what gets compiled into PlantUML.

---

## DETERMINISM ENFORCEMENT (CRITICAL)

Your code MUST enforce:

1. Canonical ordering
   - Alphabetical or topological sort
   - Stable output across runs

2. Schema validation
   - Reject malformed LLM output
   - Fail fast on hallucinations

3. Structural equivalence
   - Same IR → same UML AST → same PlantUML

4. Idempotency
   - Running the pipeline twice yields identical output

---

## PLANTUML EMISSION RULES

- PlantUML is generated ONLY from the UML AST
- No string concatenation from LLM output
- Diagram type (Context, Container, Component) is a VIEW over the AST
- Image generation is the final user-visible artifact

---

## TEST CASES (MANDATORY)

### Test 1: IR → UML Determinism
Input the same IR twice  
Expected:
- Identical UML AST
- Identical PlantUML
- Identical image

FAIL if output differs.

---

### Test 2: LLM Constrained Output
Force the LLM to return structured UML AST only  
Expected:
- JSON/schema output only
- No PlantUML text
- No prose

FAIL if free-form text appears.

---

### Test 3: Canonical Ordering
Shuffle IR input order  
Expected:
- UML output remains unchanged

FAIL if ordering affects output.

---

### Test 4: Validation & Rejection (Hallucination Defense)
Inject invalid LLM output  
Expected:
- Pipeline rejects output
- No diagram generated

FAIL if hallucination passes through.

---

### Test 5: Optimization Hook Readiness
Ensure IR → UML step allows:
- Relationship collapsing
- Component grouping
- Redundancy removal

FAIL if optimizations require IR redesign.

---

## ELIGIBILITY CRITERIA (DEFINITION OF DONE)

This task is COMPLETE only if:
 
- The LLM behaves like a compiler pass, not a generator
- Determinism is enforced by code
- UML is produced from a validated AST
- PlantUML is emitted only from code
- The system is animation-ready without redesign

If UML is generated directly by the LLM,
THIS TASK HAS FAILED.

Proceed with the implementation.