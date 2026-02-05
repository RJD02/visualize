# Build vNext: Conversational Planning Layer for Architecture Copilot

## Problem Statement
The current conversational UI accepts user requests for diagram changes,
but edits are not being applied correctly to the image.

Root cause:
- User messages are being routed directly to execution agents
- There is no intermediate reasoning step to interpret intent, scope, and target

We need to introduce a **Conversation Planning Agent** that:
- Parses user messages
- Understands intent
- Plans execution steps
- Routes actions to the correct agents

---

## High-Level Goal
Add a dedicated LLM-powered planning layer that converts free-form
user conversation into **structured execution plans**.

This agent should:
- Understand what the user is asking
- Decide whether the request is:
  - Explanation
  - Diagram type change
  - Visual edit
  - Architecture regeneration
  - Clarification required
- Decide which image/version the request refers to
- Decide which agent(s) should execute the request

---

## New Agent: ConversationPlannerAgent

### Role
Interpret conversational input and produce an **Execution Plan**.

This agent does NOT:
- Edit images
- Generate diagrams
- Modify architecture directly

It only plans and routes.

---

## Inputs to ConversationPlannerAgent

- User message (natural language)
- Current session state:
  - ArchitecturePlan
  - Available diagram types
  - Image versions (IDs, metadata)
  - Current active image ID
  - Conversation history

---

## Outputs from ConversationPlannerAgent

The agent must output a structured plan, for example:

```json
{
  "intent": "edit_image",
  "target_image_id": "img_003",
  "edit_type": "diagram_view_change",
  "instructions": "Convert this to a sequence diagram focusing on publish flow",
  "agents_to_call": ["DiagramAgent", "VisualAgent"],
  "requires_regeneration": false
}