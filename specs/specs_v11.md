# Build: Image Versioning + Conversational Rendering Guarantees
# With Unit & Integration Tests

## Problem Statement

Currently, when the user requests different diagram types or edits via conversation,
the UI image does not change reliably.

This indicates:
- Missing guarantees around image regeneration
- Missing versioning semantics
- Missing tests enforcing expected behavior

We must make image generation and versioning explicit, testable, and visible
inside the conversation flow.

---

## Goals

1. Every conversational request that changes a diagram MUST:
   - Generate a new image
   - Create a new image version
   - Be visible in the chat history

2. Images must be versioned, persisted, and referencable

3. The UI chat itself should act as the timeline:
   - Previous images appear as assistant messages
   - Users can scroll back to see all prior versions

4. Add unit and integration tests to guarantee this behavior

---

## Image Versioning Model (Conceptual)

Each image must have:
- A stable image_id
- A version number (monotonic per session)
- A parent_image_id (nullable)
- A reason (e.g., "initial generation", "converted to sequence diagram")
- A reference to the triggering conversation message

You may store images and metadata in PostgreSQL or any suitable persistence layer.

Exact schema is up to you.

---

## Conversational Rendering Rules (MANDATORY)

- Any planner intent classified as:
  - change_diagram_type
  - edit_existing_image
  - regenerate_architecture

  MUST result in:
  - A new image version
  - A new assistant message containing the image

- The UI must NOT replace images in place
- Images must be appended to the chat as new messages

Example chat flow:

User:
"Make this a sequence diagram"

Assistant:
"I'll convert the current architecture into a sequence diagram."

Assistant:
[Image v2 rendered here]

---

## UI Requirements

### Chat-Based Image Timeline

- The conversation panel must support rendering images inline
- Each image message should show:
  - Version number
  - Optional short description
- Users must be able to scroll back to see previous images

### Diagram Viewer Behavior

- The “current image” view should always reflect the latest image version
- Switching image versions should NOT mutate history

---

## Backend Behavior Guarantees

- Planner output must explicitly indicate:
  - Whether a new image is required
- Execution layer must:
  - Generate a new image if required
  - Persist it as a new version
  - Emit an assistant message referencing that image
- UI updates must be driven by persisted state, not in-memory guesses

---

## Testing Requirements (CRITICAL)

### Unit Tests

Add unit tests to validate:

1. Planner Behavior
   - Given a request like "make this a sequence diagram"
   - Planner outputs intent = change_diagram_type

2. Version Creation
   - When an execution plan requires image generation
   - A new image version is created
   - Version number increments

3. Image Lineage
   - New image references the correct parent image
   - Metadata is correctly stored

---

### Integration Tests

Add integration tests that simulate full conversations:

#### Test Case 1: Diagram Type Change

- Start session
- Generate initial architecture image
- User says: "Convert this to a sequence diagram"
- Assert:
  - A new image is generated
  - Image version count increases
  - Latest image is different from previous
  - Chat contains both images

#### Test Case 2: Multiple Edits

- User requests multiple changes in sequence
- Assert:
  - Each request produces a new image
  - Versions are ordered correctly
  - All images appear in chat history

#### Test Case 3: No-Op Requests

- User asks an explanatory question
- Assert:
  - No new image is generated
  - Image version count remains unchanged

---

## Failure Modes to Test

- Planner returns ambiguous intent → no image generated
- Image generation fails → error message appears in chat
- Image edit requested without a valid target → clarification asked

---

## Non-Goals

- Do not overwrite images in place
- Do not hide previous images
- Do not allow silent failures
- Do not rely on frontend-only state for image history

---

## Deliverables

- Image versioning implementation
- Chat-based image rendering
- PostgreSQL-backed persistence (if chosen)
- Unit tests for planner + versioning
- Integration tests simulating conversation flows
- UI changes to support image history in chat
- Documentation explaining image lifecycle