# Repair & Enhance: Conversational Multi-Image Rendering

## Problem Statement (REPAIR)

Currently, the UI displays only a single diagram image even when:
- Multiple diagrams are generated
- Multiple diagram-related assistant messages exist
- The conversation implies multiple diagram outputs

This behavior violates the intended conversational model where
diagrams are first-class messages in the chat timeline.

This must be fixed.

---

## Core Repair Requirement (NON-NEGOTIABLE)

The UI MUST render **all diagram images** that are part of the conversation history.

Specifically:
- Diagrams must appear as assistant messages inside the chat window
- Multiple diagrams must be rendered as separate messages
- No diagram should overwrite or replace a previous diagram in the UI
- Scrolling up in the conversation must reveal all previously generated diagrams

If two diagrams are generated, two images must be visible.

---

## Source of Truth Rule

The **conversation history** (persisted backend state) is the source of truth.

The UI must:
- Render messages in order
- Render image messages inline when encountered
- NOT rely on a single “current image” slot for chat rendering

A “latest image” view may exist elsewhere, but chat must show ALL images.

---

## Image Message Contract

Define a distinct message type for diagram/image messages.

Each image message must include:
- image_id
- version number
- diagram type (e.g., context, container, sequence)
- optional short explanation

The UI must render image messages differently from text messages.

---

## New Capability: User-Controlled Diagram Count (NEW)

Allow the user to specify how many diagrams they want generated.

Examples:
- “Generate 1 diagram”
- “Show me 2 diagrams”
- “I want 3 diagrams explaining this repo”

This preference must be:
- Captured from user input
- Passed into the reasoning/planning layer
- Used as a constraint, not a command

---

## Diagram Count Semantics

The system must combine:
- User preference (desired number of diagrams)
- Model reasoning (what diagrams best convey meaning)

Rules:
- The model may choose WHICH diagrams to generate
- The model must NOT exceed the user-specified count
- If fewer diagrams are sufficient, the model may generate fewer
- If user does not specify a number, the model decides freely

Example:
User: “Show me 2 diagrams”
System:
- Architecture overview
- Sequence diagram

---

## Planner Responsibilities (UPDATED)

The planner must now output:
- number_of_diagrams_requested (nullable)
- list of planned diagrams to generate
- rationale for each diagram

Example planner output:
```json
{
  "intent": "generate_diagrams",
  "diagram_count": 2,
  "diagrams": [
    { "type": "architecture", "reason": "high-level overview" },
    { "type": "sequence", "reason": "request flow clarity" }
  ]
}