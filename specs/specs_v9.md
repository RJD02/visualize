# Build: MCP-Based Tool Discovery Layer for Architecture Copilot

## Goal
Introduce Model Context Protocol (MCP) to enable dynamic tool discovery
and invocation within the Architecture Copilot system.

The system should allow LLM-based agents to:
- Discover what tools/functions are available
- Understand tool capabilities and constraints
- Select the appropriate tool(s) during planning
- Execute tools deterministically after planning

MCP must run inside the SAME server as the existing backend.

---

## Why MCP Is Being Added

Currently:
- Tool routing is hard-coded
- Planner logic must know every tool in advance
- Adding new capabilities requires code changes in multiple places

With MCP:
- Tools are discoverable
- Planner reasons over capabilities, not code paths
- System becomes extensible and agentic

---

## MCP Deployment Model (MANDATORY)

- MCP runs as an in-process service inside the main backend
- No separate deployment, container, or service
- MCP registry is initialized at server startup
- Agents access MCP via local function calls or internal HTTP

---

## MCP Responsibilities

MCP is responsible for:
1. Registering tools
2. Describing tool capabilities
3. Exposing tool schemas to LLMs
4. Executing tools when invoked

MCP is NOT responsible for:
- UI
- Business logic
- Architecture reasoning
- Agent orchestration

---

## Tools to Register via MCP (Initial Set)

At minimum, register these tools:

- extract_text
- generate_architecture_plan
- generate_plantuml
- render_image_from_plan
- edit_existing_image
- fetch_image_by_id
- list_image_versions
- explain_architecture

Each tool must include:
- Name
- Description
- Input schema
- Output schema
- Side effects (if any)

---

## Planner + MCP Interaction Model

### New Flow

1. User sends message
2. ConversationPlannerAgent is invoked
3. PlannerAgent:
   - Queries MCP for available tools
   - Reasons about which tools apply
   - Produces an Execution Plan referencing MCP tool names
4. Server executes tools via MCP
5. Results are persisted and returned to UI

---

## Execution Plan Example

```json
{
  "intent": "edit_image",
  "target_image_id": "img_004",
  "plan": [
    {
      "tool": "edit_existing_image",
      "arguments": {
        "image_id": "img_004",
        "instruction": "Increase spacing and highlight async calls"
      }
    }
  ]
}