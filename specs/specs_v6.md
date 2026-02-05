# Build v6: Agentic Architecture Visualization Platform
# Using Google ADK Runtime APIs + Interactive UI + Iterative Image Editing

## Context
google-adk is already installed and imported.

This version must:
- Execute workflows STRICTLY through Google ADK runtime APIs
- Define agents, tools, and workflows using ADK constructs
- Provide a UI that accepts:
  - Source code
  - Architecture documents (PDF, DOCX, MD)
- Generate architecture visuals
- Allow the user to ITERATIVELY EDIT THE SAME IMAGE via prompts
- Preserve architectural correctness across edits

---

## ADK Runtime Usage Pattern (MANDATORY)

Use Google ADK in this exact conceptual pattern:

- Define Agents using ADK Agent abstraction
- Define Tasks inside Agents
- Register Tools explicitly
- Use ADK Workflow / Runtime to orchestrate execution
- NO manual calling of agents outside ADK runtime

High-level ADK pattern to follow:

1. Define Agent
2. Define Tasks
3. Register Tools
4. Define Workflow
5. Execute Workflow via ADK Runtime

---

## Agent & Workflow Architecture

### Core Workflow (ADK-managed)

Input → Preprocess → ArchitectAgent → DiagramAgent → VisualAgent → EvaluatorAgent → UI

---

## Agents (ADK Definitions)

### 1️⃣ ArchitectAgent
**Type:** Reasoning Agent  
**ADK Task:** `analyzeArchitectureTask`

Responsibilities:
- Analyze extracted text (code + docs)
- Produce ArchitecturePlan JSON
- Decide diagram views
- Identify zones, relationships, boundaries

Rules:
- No UML syntax
- No class-level modeling
- Output must match ArchitecturePlan schema
- Output validated via schemaValidatorTool

---

### 2️⃣ DiagramAgent
**Type:** Deterministic / Hybrid Agent  
**ADK Task:** `generatePlantUMLTask`

Responsibilities:
- Convert ArchitecturePlan → PlantUML
- Use C4-style or component/sequence diagrams
- Render diagrams via plantumlRendererTool

Rules:
- One semantic diagram per PlantUML block
- PlantUML is canonical, not image output

---

### 3️⃣ VisualAgent
**Type:** Rendering Agent  
**ADK Task:** `generateInitialVisualTask`

Responsibilities:
- Convert ArchitecturePlan → SDXL prompt
- Call Hugging Face Inference API
- Generate initial architecture image

Rules:
- Must NOT infer or change architecture
- Must follow ArchitecturePlan strictly
- Focus on layout, grouping, arrows, readability

---

### 4️⃣ ImageEditAgent (NEW)
**Type:** Iterative Editing Agent  
**ADK Task:** `editVisualTask`

Responsibilities:
- Take existing image + user edit prompt
- Generate a refined image
- Preserve original architecture semantics

Inputs:
- Current image reference
- User edit instruction (e.g., “group services by domain”, “make arrows clearer”)

Rules:
- Do NOT add/remove components
- Do NOT change system boundaries
- Only modify visual presentation
- Always base edits on the LAST image version

This agent should use:
- SDXL image-to-image mode (if available)
- Or prompt-based refinement with strong constraints

---

### 5️⃣ EvaluatorAgent
**Type:** Control / Guard Agent  
**ADK Task:** `evaluateOutputsTask`

Responsibilities:
- Validate:
  - ArchitecturePlan correctness
  - PlantUML alignment
  - Image vs plan consistency
- Decide:
  - Accept
  - Retry (which agent)
  - Reject with diagnostics

---

## Tools (Registered with ADK)

- `textExtractorTool`
  - Supports: PDF, DOCX, MD, source code
- `schemaValidatorTool`
- `plantumlRendererTool`
- `sdxlTextToImageTool`
- `sdxlImageToImageTool` (for edits)
- `fileStorageTool`
- `imageVersioningTool` (tracks image history)

Agents may ONLY interact with the world via tools.

---

## ADK Workflow Definition

Define a single ADK workflow:

1. Extract input text
2. ArchitectAgent → ArchitecturePlan
3. Validate ArchitecturePlan
4. DiagramAgent → PlantUML diagrams
5. VisualAgent → Initial image
6. EvaluatorAgent → Validate
7. Return result to UI

For image edits:
- Invoke ImageEditAgent ONLY
- Do NOT re-run ArchitectAgent
- Preserve ArchitecturePlan
- Store image versions

---

## UI Requirements (NEW)

### UI Stack
- Web-based UI (React preferred)
- Backend API connected to ADK runtime

### UI Features

#### 1️⃣ Input Panel
- Upload:
  - Code files
  - PDF / DOCX / MD
- Or paste text/code
- “Generate Architecture” button

#### 2️⃣ Output Panel
- Show:
  - Generated architecture image
  - Diagram view selector (optional)
- Display image version history (v1, v2, v3…)

#### 3️⃣ Edit Panel (Key Feature)
- Text input: “Edit the diagram…”
- Button: “Apply Edit”
- Each edit:
  - Calls ImageEditAgent
  - Produces a NEW image version
  - Replaces displayed image
  - Preserves architecture

Examples:
- “Group services by domain”
- “Increase spacing between components”
- “Make external systems dashed”
- “Use left-to-right layout”

#### 4️⃣ Reset / Revert
- Allow reverting to earlier image versions
- ArchitecturePlan remains immutable unless regenerated

---

## Output Contract (API → UI)

{
  "architecture_plan": ArchitecturePlan,
  "plantuml_files": [...],
  "images": [
    { "version": 1, "file": "arch_v1.png" },
    { "version": 2, "file": "arch_v2.png" }
  ],
  "evaluation": {
    "score": number,
    "warnings": string[]
  }
}

---

## Non-Goals (STRICT)

- Do NOT let UI directly prompt the LLM
- Do NOT regenerate architecture during edits
- Do NOT allow image edits to change system semantics
- Do NOT bypass ADK runtime orchestration

---

## Documentation Requirements

- Explain ADK runtime flow
- Explain why ArchitecturePlan is immutable
- Explain image editing vs regeneration
- Document agent responsibilities clearly
- Provide example: NPM + Network Performance Management Tool

---

## Deliverables

- ADK-based workflow implementation
- ImageEditAgent implementation
- UI with upload, generate, edit, revert
- Image versioning logic
- README explaining end-to-end flow