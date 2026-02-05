# Build: GitHub Repository Ingestion as an Input Source for Architecture Copilot

## Goal
Extend the Architecture Copilot system to accept a GitHub repository URL
as an input source, automatically ingest the repository, analyze its contents,
and generate one or more architecture or flow diagrams that best represent
the system.

The experience should feel equivalent to pasting architecture text or
uploading documents, but powered by real code structure.

---

## Core Capability

Users should be able to:
- Paste a GitHub repository URL
- Have the system fetch the repository (if accessible)
- Analyze the codebase and structure
- Reason about the system architecture or flows
- Generate one or more visual diagrams
- Refine those diagrams conversationally

---

## Supported Repository Types

At minimum, support:
- Public GitHub repositories
- Repositories accessible via HTTPS clone
- Monorepos and single-service repos

Authentication handling (tokens, private repos) may be designed if needed,
but public repos must work by default.

---

## New Tool: GitHub Repository Ingestion Tool

Introduce a new tool that:
- Accepts a GitHub repository URL
- Downloads or clones the repository
- Extracts relevant signals from the repo

This tool should:
- Ignore irrelevant files (node_modules, vendor, build outputs)
- Respect repository structure
- Be safe (no arbitrary code execution)

The output of this tool should be a **normalized repository representation**
that can be used as input for reasoning agents.

---

## Repository Analysis Expectations

The system should be able to reason about:
- Folder structure
- Entry points
- Service boundaries
- APIs, modules, and layers
- Configuration files (e.g., package.json, docker-compose, k8s, CI files)
- Data flow hints (imports, calls, routes, messaging)

Exact parsing strategy is up to you.

The goal is **architectural understanding**, not full semantic correctness.

---

## Agent Integration

### Planner + MCP Integration

- The ConversationPlannerAgent must be able to discover the GitHub ingestion tool
  via MCP.
- Planner decides when a GitHub URL is present and which tool to invoke.
- Planner must decide:
  - Whether to generate a single diagram or multiple diagrams
  - Which diagram types are appropriate (architecture, flow, sequence, etc.)

---

### Architecture Reasoning

After repository ingestion:
- Architecture reasoning should operate on the extracted repo representation
- The system should infer:
  - High-level architecture (services, layers, boundaries)
  - Key flows (request lifecycle, build/deploy, data movement)

The system may generate:
- One primary architecture diagram
- Optional secondary diagrams (e.g., request flow, CI/CD flow)

---

## Diagram Generation Expectations

- Diagrams should represent the repository meaningfully
- Avoid class-level diagrams unless explicitly requested
- Prefer:
  - System / container / component views
  - Flow or sequence views when appropriate

Multiple diagrams are allowed and encouraged if they clarify the system.

---

## Persistence & Referencing

- Generated diagrams must be stored with:
  - Image IDs
  - Source metadata (GitHub repo, commit hash or timestamp)
  - Parent-child relationships (if derived)
- Users should be able to refer to:
  - “the GitHub diagram”
  - “the second diagram”
  - “the one showing the API flow”

Conversation should resolve these references correctly.

---

## UI Changes

Update the UI to support:
- A GitHub URL input option alongside existing inputs
- Clear indication that the source is a GitHub repository
- Display of repo name and branch/commit used
- Generated diagrams shown as normal image outputs

The user experience should not require understanding Git internals.

---

## Conversational Refinement

After diagrams are generated:
- Users should be able to:
  - Ask questions about the repository architecture
  - Request visual edits
  - Request alternative views
  - Request regeneration with a different focus

Conversation must remain stateful and refer to stored images.

---

## Workflow Expectations

End-to-end flow should be:

1. User provides GitHub repo URL
2. Planner identifies GitHub input
3. GitHub ingestion tool is invoked
4. Repository is analyzed
5. Architecture reasoning occurs
6. One or more diagrams are generated
7. Diagrams are persisted
8. User enters conversational refinement loop

---

## Design Principles

- GitHub ingestion is just another input modality
- Architecture reasoning remains the central intelligence
- Tools are discoverable via MCP, not hard-coded
- Conversation drives refinement, not raw prompts
- System should be extensible to other code hosts later

---

## Non-Goals

- Do not execute repository code
- Do not attempt full static analysis
- Do not require perfect architectural inference
- Do not expose raw repository contents directly to the UI

---

## Deliverables

- GitHub ingestion tool
- Planner integration with GitHub input
- Repository analysis pipeline
- Architecture diagram generation from repos
- UI support for GitHub URLs
- Documentation explaining repo-based workflows