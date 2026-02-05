# Build v4: Agentic Architecture Visualization System using Google ADK

## Goal
Implement an agent-based architecture visualization system using
Google Agent Development Kit (ADK) as the orchestration runtime.
We will use plantUML only. Remove other LLMs code scripts.
The system must:
- Accept source code and .docx architecture documents
- Reason about system architecture using an Architect Agent
- Generate a structured Architecture Plan (JSON)
- Render:
  - Technical diagrams via PlantUML
  - Visual diagrams via SDXL (Hugging Face inference)
- Use ADK to define agents, tools, workflows, and state
- Minimize ad-hoc prompting by encoding behavior in agent logic

ADK should be used as an EXECUTION FRAMEWORK, not as the core domain model.

---

## Architectural Principles (STRICT)

1. Architecture Plan JSON is the single source of truth
2. Agents are stateful, tool-driven, and orchestrated
3. LLMs are used ONLY for reasoning, not control flow
4. Prompts must be embedded inside agent tasks, not user-authored
5. All agent inputs/outputs must be schema-validated

---

## High-Level Architecture

Input (code / docx)
  ↓
Preprocessor (extract & normalize text)
  ↓
ADK Orchestrator
  ↓
Architect Agent  ──→ Architecture Plan JSON
  ↓
Diagram Agent    ──→ PlantUML text
  ↓
Visual Agent     ──→ SDXL prompt → image
  ↓
Evaluator Agent  ──→ quality checks
  ↓
Final Output

---

## Core Data Model (Framework-Agnostic)

Define these as plain TypeScript / Python models (NOT ADK-specific):

ArchitecturePlan {
  system_name: string
  diagram_views: string[]
  zones: {
    clients: string[]
    edge: string[]
    core_services: string[]
    external_services: string[]
    data_stores: string[]
  }
  relationships: [
    {
      from: string
      to: string
      type: "sync" | "async" | "data" | "auth"
      description: string
    }
  ]
  visual_hints: {
    layout: "left-to-right" | "top-down"
    group_by_zone: boolean
    external_dashed: boolean
  }
}

This model must NOT depend on ADK.

---

## Agent Definitions (Using ADK)

### 1. ArchitectAgent (Reasoning Agent)

Responsibility:
- Analyze normalized input text
- Decide architectural views
- Identify zones, components, relationships
- Produce ArchitecturePlan JSON

ADK Task:
- analyzeArchitectureTask

Embedded reasoning instruction (NOT exposed to user):

"""
You are a senior software architect.
Analyze the system at an architectural level.
Think in terms of responsibilities, boundaries, and data flow.
Do not describe classes or methods.
Output only valid ArchitecturePlan JSON.
"""

---

### 2. DiagramAgent (Deterministic Agent)

Responsibility:
- Convert ArchitecturePlan → PlantUML

Implementation:
- Mostly deterministic code
- Optional LLM assistance for layout hints

ADK Task:
- generatePlantUMLTask

Rules:
- Prefer C4-style or component diagrams
- No class diagrams unless explicitly required
- One semantic diagram type per PlantUML block

---

### 3. VisualAgent (Rendering Agent)

Responsibility:
- Convert ArchitecturePlan → SDXL prompt
- Call Hugging Face Inference API

ADK Task:
- generateVisualDiagramTask

Rules:
- Must NOT infer architecture
- Must follow ArchitecturePlan strictly
- Focus on grouping, arrows, layout, readability
- White/light background, professional diagram style

SDXL model:
stabilityai/stable-diffusion-xl-base-1.0

---

### 4. EvaluatorAgent (Quality Gate)

Responsibility:
- Validate ArchitecturePlan and outputs

Checks:
- No class-level artifacts in architecture plans
- Druid / DB / CDN classified correctly
- External services marked as external
- Diagrams align with selected views

Evaluator decides:
- accept
- retry ArchitectAgent
- fail with diagnostics

---

## Tool Definitions (ADK Tools)

Define tools explicitly and register them with ADK:

- textExtractorTool (docx, code)
- plantumlRendererTool
- sdxlInferenceTool (Hugging Face)
- schemaValidatorTool
- fileStorageTool

Agents may ONLY act via registered tools.

---

## Orchestration Logic (ADK Workflow)

Use ADK workflow to define:

1. Extract input text
2. Run ArchitectAgent
3. Validate ArchitecturePlan
4. Run DiagramAgent
5. Run VisualAgent
6. Run EvaluatorAgent
7. Return results

Retries:
- ArchitectAgent may retry up to N times
- DiagramAgent must be deterministic
- VisualAgent failures must not block PlantUML output

---

## Output Contract

{
  "architecture_plan": ArchitecturePlan,
  "plantuml": {
    "files": ["component.puml", "sequence.puml"]
  },
  "visual": {
    "sdxl_prompt": "string",
    "image_file": "architecture.png"
  },
  "evaluation": {
    "score": number,
    "warnings": string[]
  }
}

---

## Folder Structure

/agents
  architect_agent.ts
  diagram_agent.ts
  visual_agent.ts
  evaluator_agent.ts

/tools
  text_extractor.ts
  plantuml_renderer.ts
  sdxl_renderer.ts
  validator.ts

/orchestrator
  adk_workflow.ts

/models
  architecture_plan.ts

---

## Non-Goals (STRICT)

- Do NOT let agents talk to each other freely
- Do NOT allow free-form text outputs
- Do NOT hard-code prompts in user-facing code
- Do NOT depend on ADK types in core models

---

## Documentation Requirements

- Explain why ArchitecturePlan is canonical
- Explain ADK’s role vs domain logic
- Provide example run using NPM and Network Performance Management docx
- Document how to swap ADK with another runtime

---

## Deliverables

- ADK-based multi-agent workflow
- ArchitecturePlan schema
- SDXL integration via Hugging Face
- Example outputs
- README explaining agent responsibilities