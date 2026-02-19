You are a senior frontend + backend architect.
Refactor the application so that:
    1.  All user interactions are handled through a single Chat interface.
    2.  All backend responses are returned through a unified response envelope.
    3.  The UI renders everything (diagram, analysis, animation, edits) inside the chat window.
    4.  Remove feature-specific overlays or multi-panel rendering logic.
    5.  Introduce a single API endpoint (REST or GraphQL) that acts as the orchestration gateway.
This is not a cosmetic change. This is an architectural refactor.
Implement the following:
⸻
PART 1 — Introduce Unified Response Envelope
Every backend response must follow this schema:
{
"response_type": "diagram | analysis | text | mixed | animation",
"blocks": [
{
"block_type": "text | diagram | analysis | animation | action",
"payload": {…}
}
],
"state": {
"ir_version": number,
"has_diagram": boolean,
"analysis_score": number | null
},
"confidence": number
}
Rules:
    •   No raw unstructured responses.
    •   No feature-specific JSON outside this envelope.
    •   If invalid schema, reject before returning to UI.
⸻
PART 2 — Single Orchestration Endpoint
Create a single endpoint:
POST /api/chat
Input:
{
"message": string,
"current_ir": optional IR,
"conversation_id": string
}
The orchestrator must:
    •   Detect intent
    •   Route internally to visual_agent or review_agent
    •   Wrap response in unified envelope
    •   Return to UI
UI must never call:
    •   /render
    •   /analyze
    •   /animate
    •   /edit
All must go through /api/chat.
⸻
PART 3 — Frontend Refactor
Modify UI so:
    1.  Only ChatWindow component exists as main surface.
    2.  Remove secondary windows or overlays.
    3.  Implement message renderer that maps:
block_type === "text" → render markdown
block_type === "diagram" → render SVG component
block_type === "analysis" → render structured analysis card
block_type === "animation" → render animated SVG inline
block_type === "action" → render buttons (apply patch, preview, etc.)
All rendering must happen inside chat message container.
No modal overlays.
No floating animation windows.
⸻
PART 4 — Animation Handling
When user says:
"Animate this"
Orchestrator routes to visual_agent.
Response envelope:
{
"response_type": "animation",
"blocks": [
{ "block_type": "animation", "payload": { animated_svg: "…"} }
]
}
UI renders animated SVG inline inside chat message.
Remove existing animation overlay logic.
⸻
PART 5 — Diagram Rendering
When diagram is generated:
{
"response_type": "diagram",
"blocks": [
{ "block_type": "diagram", "payload": { svg: "…", ir_version: n } }
]
}
Chat message displays diagram.
Do not replace entire UI.
Do not open new window.
⸻
PART 6 — Analysis Rendering
When architecture review is requested:
{
"response_type": "analysis",
"blocks": [
{
"block_type": "analysis",
"payload": {
"score": number,
"issues": […],
"suggested_patches": […]
}
}
]
}
UI renders analysis card inline.
If suggested_patches exist:
Render action buttons within that message.
⸻
PART 7 — State Management
Frontend must maintain:
    •   current IR
    •   ir_version
    •   conversation history
But rendering is driven only by blocks from server.
Never derive rendering logic from user message alone.
⸻
PART 8 — Remove Legacy Feature-Specific Routing
Search codebase and remove:
    •   Dedicated animation routes
    •   Dedicated render endpoints
    •   Dedicated analysis endpoints
    •   Overlay rendering logic
Everything must pass through orchestrator.
⸻
PART 9 — Testing Requirements
Add tests to verify:
    1.  Sending "generate diagram" returns diagram block.
    2.  Sending "analyze architecture" returns analysis block.
    3.  Sending "animate this" returns animation block.
    4.  Sending random text returns text block.
    5.  Mixed response returns multiple blocks in order.
    6.  UI renders correct component for each block_type.
    7.  No overlay component is used anywhere.
    8.  No legacy endpoints are called from UI.
⸻
PART 10 — Final Goal
After refactor:
    •   Only one visible window: Chat.
    •   All diagrams appear as message blocks.
    •   All animations appear inline.
    •   All analysis appears inline.
    •   One endpoint orchestrates everything.
    •   Backend agents remain modular.
    •   UI is decoupled from internal agent architecture.
Do not break existing IR logic.
Do not break versioning.
Do not break styling agent.
Perform this refactor incrementally.
Ensure tests pass before removing old paths.
