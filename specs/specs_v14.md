# Build: Deterministic Diagram IR (SVG-as-IR) with Strict Rules + Versioned Editing in Conversation

## Goal
Introduce a deterministic Intermediate Representation (IR) for diagrams so that:
- Diagrams are stored and edited as IR, not raw images
- Small IR changes produce small visual changes
- IR is versioned alongside the conversation
- User requests result in IR edits, followed by deterministic rendering into SVG/PNG for UI display

The IR must be "SVG-as-IR" (SVG structured with strict semantic rules),
not arbitrary raw SVG.

This IR will become the foundation for future animation IR, but for now focus on static diagrams.

---

## Core Concepts (NON-NEGOTIABLE)

### IR Requirements (SVG-as-IR Rules)
The IR must enforce these rules:

1) Every semantic element MUST be a `<g>` group with:
   - a stable `id` (stable across edits)
   - `data-kind` (e.g., "node", "edge", "boundary", "label", "legend")
   - `data-role` (e.g., "service", "db", "client", "external", "auth", "queue")

2) No anonymous paths:
   - Every `<path>`, `<rect>`, `<text>`, `<line>`, etc. must be inside a `<g id="...">`
   - Each primitive must have its own id or inherit the parent group id with suffix convention

3) No absolute colors without semantic tokens:
   - Disallow hard-coded hex colors except in a predefined token map
   - Use CSS variables or named tokens (e.g., `var(--color-service)`)
   - All styles must reference semantic tokens

4) No inline animation:
   - No `<animate>`, `<animateTransform>`, SMIL, or inline CSS keyframes
   - Future animation will be layered later

5) No transforms without semantic reason:
   - Disallow arbitrary `transform="translate(...)"` unless it is tied to a semantic layout rule
   - Prefer explicit x/y coordinates in attributes or a layout section
   - If transforms exist, they must include metadata such as `data-transform-reason="layout:grid"` or similar

---

## System Behavior Changes

### New Source of Truth
- The IR (SVG-as-IR) becomes the canonical artifact for each diagram version
- PNG is only a rendered output (cache), not the editable source
- Every diagram message in chat should be backed by an IR version

### Versioning
- Persist IR versions as the conversation progresses
- Each IR version must have:
  - ir_id (stable)
  - version number (monotonic per session)
  - parent_version (lineage)
  - reason ("initial generation", "edit: group services", etc.)
  - associated conversation message id

### Deterministic Rendering
- Rendering pipeline must be deterministic:
  - Same IR -> same SVG output
  - Small IR change -> localized SVG changes
- Renderer must preserve stable element ids and group structure

---

## Workflow Requirements

### Initial Generation Flow
1) User provides input (text/doc/repo)
2) System generates architecture understanding (existing flow)
3) System generates diagram IR (SVG-as-IR) as canonical output
4) System validates IR against the rule set
5) System renders:
   - SVG (direct from IR)
   - PNG (optional for preview)
6) System appends a chat message containing the rendered diagram

### Edit Flow (IMPORTANT)
All edits must modify IR, not images:

1) User asks for a change (via conversation)
2) Planner decides if this is an IR edit request
3) IR Edit Agent produces a patch / modification to the IR (not a new random SVG)
4) Validate the new IR against rules
5) Render new SVG/PNG
6) Append new diagram message in chat with version+metadata

---

## New Components / Tools (Let Codex decide exact structure)

### 1) IR Validator
- A strict validator that checks the SVG-as-IR rule set
- Reject invalid IR with actionable errors
- Tests must cover all rules

### 2) IR Renderer
- Deterministically renders SVG from IR
- Optionally rasterizes to PNG for UI display
- Must preserve stable ids and semantic groups

### 3) IR Edit Agent / Tool
- A tool registered in MCP such as: `edit_diagram_ir`
- Input:
  - current IR (or IR reference id/version)
  - user instruction
  - optional constraints (diagram type, layout preference)
- Output:
  - IR patch or full updated IR
- Requirements:
  - MUST make minimal changes where possible
  - MUST preserve stable ids for unchanged elements
  - MUST not restructure unrelated groups
  - MUST not introduce forbidden SVG features

The model should decide when to use this tool.

### 4) IR Diff / Patch (Recommended)
- Represent edits as a patch operation (e.g., JSON patch, custom patch DSL, or minimal SVG diff)
- Apply patch deterministically to previous IR version
- Store patches for debugging and rollback

---

## UI Requirements

- Conversation window must show each diagram as an inline message
- Each diagram message should display:
  - diagram type
  - version number
  - IR version reference (optional visible)
- Allow user to click an older diagram and “branch” edits from it

The main viewer can show the latest diagram, but chat is the timeline.

---

## Persistence Requirements

- Store IR versions in a database (Postgres recommended)
- Store rendered SVG (and optional PNG) as artifacts linked to IR version
- Store conversation messages and link diagram messages to IR versions

Let Codex decide schemas, but ensure referential integrity between:
session -> messages -> ir_versions -> rendered_artifacts

---

## Eligibility Criteria (Definition of Done)

This feature is considered correct only if:

1) ✅ IR is generated and stored for every diagram (SVG-as-IR)
2) ✅ IR passes all enforced rules via validator
3) ✅ Edits modify IR (not raw image) and create new IR versions
4) ✅ Stable ids are preserved for unchanged elements across edits
5) ✅ Small IR changes cause localized SVG diffs (measured via tests)
6) ✅ Conversation shows multiple diagrams as history (no overwrite)
7) ✅ Unit tests exist for:
   - validator rules
   - versioning
   - stable-id preservation
   - deterministic rendering output
8) ✅ Integration tests simulate:
   - generate -> edit -> edit -> revert/branch
   - ensuring multiple IR versions and multiple diagram messages appear

If any of these fail, the implementation is incomplete.

---

## Testing Requirements (MANDATORY)

### Unit tests must cover:
- Each IR rule (fail cases + pass cases)
- Stable id preservation across edits
- Token enforcement (no raw hex unless in approved token map)
- No anonymous paths rule enforcement
- Transform rule enforcement

### Integration tests must cover:
- Generate initial IR + render and display in chat
- Make an edit request and verify:
  - IR version increments
  - new diagram message is appended to chat
  - previous diagram still visible
- Ensure deterministic re-render:
  - render(IR vN) twice -> identical SVG output

---

## Non-Goals
- Do not implement animation yet
- Do not allow arbitrary SVG passthrough
- Do not let the UI edit SVG directly
- Do not store only PNG; IR must be canonical

---

## Deliverables
- SVG-as-IR format + rules implementation
- IR validator + tests
- IR renderer + tests
- IR edit tool integrated via MCP
- Versioned IR storage and linkage to conversation messages
- Updated UI to render diagrams as conversation artifacts
- Documentation describing IR rules and how edits work
