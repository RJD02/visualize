You are an autonomous senior full-stack engineer.

Goal:
Implement animation as a post-processing layer over existing SVG diagrams, following this philosophy:
- IR defines semantics
- SVG defines static structure/layout
- Presentation (animation, color, emphasis) is a separate, detachable layer
Animation must NOT affect structure.

Existing system:
- Server already generates IR and static SVG from IR
- UI already renders static SVG
- We need to add:
  1) A Presentation / Animation Spec
  2) An animation resolver on top of SVG
  3) A UI toggle to switch between static and animated modes

Hard constraints:
- SVG remains the source of truth
- Animation is declarative
- Animation must be removable without regenerating SVG
- No layout or geometry changes in animation
- Prefer CSS-based animation on SVG
- Keep it minimal, extensible, and testable

----------------------------------------------------------------
STEP 1: Define Presentation / Animation Spec
----------------------------------------------------------------

Create a schema (JSON or YAML) called PresentationSpec with:
- version
- targets (array)
Each target includes:
- selector (CSS selector targeting SVG elements)
- styles (fill, stroke, opacity, etc.)
- animation (optional):
  - type (pulse | draw | fade | flow | highlight)
  - duration
  - delay
  - easing
  - repeat

Example (store under /specs/presentation/example.json):

{
  "version": 1,
  "targets": [
    {
      "selector": ".node",
      "styles": { "fill": "#E5E7EB" }
    },
    {
      "selector": "#node-api",
      "styles": { "fill": "#6366F1" },
      "animation": {
        "type": "pulse",
        "duration": "1.5s",
        "easing": "ease-in-out",
        "repeat": "infinite"
      }
    },
    {
      "selector": ".edge-request",
      "animation": {
        "type": "draw",
        "duration": "800ms",
        "delay": "200ms"
      }
    }
  ]
}

----------------------------------------------------------------
STEP 2: Server-side animation resolver
----------------------------------------------------------------

On the server:
- Add a module: animationResolver.ts (or equivalent)

Responsibilities:
- Take inputs:
  - static SVG string
  - PresentationSpec
- Validate:
  - selectors exist in SVG
  - animation types are supported
- Generate:
  - <style> block with CSS animations
  - Optional SVG <defs> if needed
- Inject styles into SVG <style> tag
- Return animated SVG

Rules:
- Must not add/remove SVG elements
- Must not modify viewBox, paths, coordinates
- Only styles, classes, animations

Implement supported animation primitives:
- pulse → scale + opacity oscillation
- draw → stroke-dasharray / dashoffset animation
- fade → opacity transition
- highlight → temporary color emphasis

Expose an endpoint:
POST /api/diagram/render
Body:
{
  "mode": "static" | "animated",
  "ir": {...},
  "presentationSpec": {...} (only used if animated)
}

Response:
{
  "svg": "<svg>...</svg>"
}

----------------------------------------------------------------
STEP 3: UI toggle (Static / Animated)
----------------------------------------------------------------

In the UI:
- Add a toggle button or switch:
  Label: "Animation"
  States:
    OFF → Static Diagram
    ON → Animated Diagram

Behavior:
- OFF:
  - Call render API with mode=static
  - Render SVG as-is
- ON:
  - Call render API with mode=animated
  - Pass PresentationSpec
  - Render returned animated SVG

Implementation notes:
- Toggle should not re-run IR generation
- Only affects rendering layer
- Preserve zoom / pan / viewport state

----------------------------------------------------------------
STEP 4: UI rendering details
----------------------------------------------------------------

Ensure:
- SVG is injected via <div dangerouslySetInnerHTML> or equivalent
- CSS animations are scoped to the SVG only
- No global CSS pollution

Add optional:
- Reduced motion support:
  - If prefers-reduced-motion is detected, force static mode

----------------------------------------------------------------
STEP 5: Testing & validation
----------------------------------------------------------------

Add tests:
- Static SVG snapshot remains unchanged when animation is OFF
- Animated SVG contains:
  - <style> with keyframes
  - No geometry differences
- Selector validation errors are reported clearly
- Toggling does not regenerate IR

----------------------------------------------------------------
STEP 6: Deliverables
----------------------------------------------------------------

Produce:
- PresentationSpec schema + example
- animationResolver implementation
- API endpoint wiring
- UI toggle + wiring
- README section explaining:
  - IR vs SVG vs Presentation
  - How to add new animation primitives

Proceed to implement. Make reasonable assumptions where details are missing, but document them clearly in code comments.


----------------------------------------------------------------
STEP 7: Eligibility criteria (definition of DONE)
----------------------------------------------------------------

The implementation is considered ELIGIBLE and COMPLETE only if ALL the following are true:

ARCHITECTURAL ELIGIBILITY
1. IR generation logic is unchanged.
2. Static SVG generation output is byte-identical before and after this change when animation is OFF.
3. Presentation / Animation logic exists as a separate layer/module.
4. Animation does not modify:
   - SVG structure
   - Element count
   - Paths, coordinates, viewBox, transforms related to layout
5. Animation can be completely disabled without regenerating IR or SVG.
6. PresentationSpec is declarative (no imperative timelines in source of truth).

API ELIGIBILITY
7. API supports both:
   - mode=static
   - mode=animated
8. Animated mode ONLY differs by:
   - injected <style> and/or <defs>
   - class/style attributes
9. Invalid PresentationSpec fails gracefully with clear errors.

UI ELIGIBILITY
10. UI includes a toggle (Static / Animated).
11. Toggling animation does NOT:
    - re-run IR generation
    - change layout
    - reset zoom/pan state
12. Reduced-motion users always receive static SVG.

QUALITY ELIGIBILITY
13. Animation primitives are reusable and extensible.
14. Code is commented where assumptions are made.
15. README documents the layering philosophy clearly.

----------------------------------------------------------------
STEP 8: Explicit success criteria
----------------------------------------------------------------

SUCCESS is defined as:

- When animation toggle is OFF:
  - The rendered SVG matches the static SVG snapshot exactly.
  - No animation-related CSS or keyframes exist in DOM.

- When animation toggle is ON:
  - SVG visually animates according to PresentationSpec.
  - Animation is smooth, deterministic, and repeatable.
  - All animated elements are selected ONLY via CSS selectors.
  - No DOM nodes are added or removed.

- PresentationSpec can be modified (e.g., colors, durations)
  WITHOUT changing IR or SVG generation code.

- A developer can add a new animation primitive
  by editing ONLY the animation resolver module.

----------------------------------------------------------------
STEP 9: Test cases (Codex must implement or simulate)
----------------------------------------------------------------

Create automated or scripted tests for the following cases.

--- TEST CASE 1: Static mode integrity ---
Given:
- Same IR input
- mode=static

Assert:
- SVG output hash before and after animation feature is identical
- No <style> tag related to animation exists
- No @keyframes present

--- TEST CASE 2: Animated mode injection ---
Given:
- Same IR input
- mode=animated
- Valid PresentationSpec

Assert:
- SVG structure (elements count, paths) is unchanged
- <style> tag contains keyframes
- CSS selectors match existing SVG elements
- Animation properties match spec (duration, easing, repeat)

--- TEST CASE 3: Toggle behavior ---
Given:
- UI loaded with static diagram
- Toggle switched ON

Assert:
- No IR regeneration call is made
- Only render endpoint is called
- SVG updates visually
- Zoom/pan state preserved

Then:
- Toggle switched OFF
Assert:
- Animated styles removed
- Static SVG restored

--- TEST CASE 4: Selector validation ---
Given:
- PresentationSpec with invalid selector

Assert:
- Server responds with 4xx error
- Error message includes missing selector
- Static rendering still works

--- TEST CASE 5: Reduced motion ---
Given:
- prefers-reduced-motion = true
- Animation toggle ON

Assert:
- Server or UI forces static mode
- No animation CSS applied

--- TEST CASE 6: Non-structural guarantee ---
Given:
- Animated SVG output
- Static SVG output

Assert:
- DOM diff ignoring <style> and class/style attributes is empty

--- TEST CASE 7: Extensibility check ---
Given:
- New animation primitive added (e.g., glow)

Assert:
- No changes needed in IR or SVG generation
- Only animation resolver modified

----------------------------------------------------------------
STEP 10: Failure conditions (explicit)
----------------------------------------------------------------

FAIL the task if ANY of the following occur:

- Animation logic alters layout or geometry.
- Static SVG output changes when animation is OFF.
- Animation logic is mixed into IR generation.
- UI toggle triggers IR regeneration.
- Animation is imperative JS without declarative spec.
- Reduced-motion preference is ignored.
- No clear separation between SVG generation and animation logic.

----------------------------------------------------------------
STEP 11: Final verification artifact
----------------------------------------------------------------

Produce a file:
.artifacts/animation-verification-report.md

Include:
- Eligibility checklist (pass/fail)
- Test case results
- Known limitations
- Next steps (e.g., GIF export, timelines)

Only mark the task COMPLETE if all eligibility criteria pass.