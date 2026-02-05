# Build: Conversational, Multi-Diagram Architecture Reasoning System

## Goal
Evolve the Architecture Copilot into a conversational system where:
- Diagrams are generated as part of the conversation itself
- The system can decide to generate ONE or MULTIPLE diagrams
- Diagrams are versioned, persisted, and scrollable in chat history
- Users can iteratively refine diagrams through conversation
- Image edits are intelligent and architecture-aware

The system should feel like:
“ChatGPT, but where diagrams are first-class conversational messages.”

---

## Core Capabilities

### 1. Multi-Diagram Reasoning (NEW)

The system must be able to decide whether:
- A single diagram is sufficient, OR
- Multiple diagrams are required to convey meaning

Examples:
- Architecture overview → multiple diagrams (context + container)
- Code repo → architecture + flow + sequence
- Event-driven system → architecture + async flow

This decision should be made by the LLM based on:
- Input text
- Code repository structure
- Complexity and domain signals

No fixed rules; the model must reason about clarity.

---

### 2. Conversational Diagram Rendering (CRITICAL)

Diagrams must be rendered:
- INSIDE the conversation timeline
- As assistant messages, not in a separate static panel

Each diagram message must:
- Contain the rendered image
- Have a version number
- Have a short explanation (why this diagram exists)

Users must be able to:
- Scroll up to see all previously generated diagrams
- Refer to diagrams by position or version in conversation

Example:

Assistant:
“I’ll start with a high-level architecture diagram.”

[Diagram v1]

Assistant:
“Now I’ll add a sequence diagram to explain the publish flow.”

[Diagram v2]

---

### 3. Versioned Conversation + Versioned Images

The system must maintain:
- A versioned conversation history
- A versioned image history linked to conversation turns

Each diagram must be associated with:
- A conversation message ID
- A version number
- A parent diagram (if derived)
- A reason (e.g., “clarifies async flow”)

Persistence can use PostgreSQL or equivalent.

---

## New Capability: Intelligent Image Editing Tool (NEW)

Introduce a new tool registered via MCP:

### Tool: edit_diagram_via_semantic_understanding

This tool:
- Takes an existing diagram image
- Understands its visual and textual content
- Accepts a user’s conversational suggestion
- Translates the suggestion into:
  - Updated UML or diagram representation
  - Then renders a new diagram image

This tool should:
- NOT blindly redraw the image
- Understand components, relationships, and layout
- Preserve architectural correctness unless explicitly changed

The LLM must decide WHEN this tool is appropriate.

---

## MCP Integration (IMPORTANT)

- Register all diagram-related tools with MCP, including:
  - generate_diagram
  - generate_multiple_diagrams
  - edit_diagram_via_semantic_understanding
- Planner / reasoning layer must:
  - Discover available tools via MCP
  - Decide which tool(s) to invoke
- Execution must be deterministic once planned

The UI must never directly invoke tools.

---

## Updated Conversational Workflow

1. User provides input (text, doc, or GitHub repo)
2. System reasons about architecture
3. System decides:
   - Number of diagrams needed
   - Types of diagrams needed
4. Diagrams are generated sequentially
5. Each diagram appears as an assistant message
6. User converses:
   - Asks questions
   - Requests edits
   - Requests alternative views
7. Planner decides whether to:
   - Explain
   - Generate a new diagram
   - Edit an existing diagram
8. New diagrams are appended to conversation

---

## UI Requirements (React + TailwindCSS)

### Conversation-Centric UI (MANDATORY)

- The conversation panel is the PRIMARY surface
- Images appear inline in chat bubbles
- Each image bubble shows:
  - Diagram type
  - Version number
- Image viewer panel (optional) can show the latest image,
  but must not replace the conversational timeline

---

### Image Version Navigation

- Users can scroll to see older images
- Users can refer to images conversationally:
  “In the second diagram…”
  “Edit the last sequence diagram…”

The system must resolve these references correctly.

---

## Backend Expectations

- Persist:
  - Conversations
  - Diagram images
  - Diagram metadata
- Link diagrams to conversation messages
- Support multi-diagram sessions
- Support multi-step reasoning per user message

---

## Design Principles

- Diagrams are conversational artifacts, not static outputs
- The model decides how many diagrams are needed
- Editing is semantic, not pixel-based
- Versioning is explicit and persistent
- Reasoning precedes rendering

---

## Non-Goals

- Do not force one diagram per request
- Do not overwrite diagrams in place
- Do not hide diagrams outside conversation
- Do not let the UI decide diagram logic

---

## Deliverables

- Multi-diagram reasoning logic
- Conversational diagram rendering
- Versioned conversation + image persistence
- MCP-registered image editing tool
- UI updates to support inline diagram history
- Documentation explaining diagram lifecycle