# Build v3.1: Dual-Output Architecture Visualization System
# (PlantUML + Hugging Face Stable Diffusion XL)

## Context
We already have a system that:
- Accepts source code and .docx architecture documents
- Uses an LLM to reason about the system architecture
- Automatically decides which architectural views are appropriate
- Generates PlantUML diagrams and renders them

We now want to:
- Replace DALL·E with **Hugging Face Inference API**
- Use **stabilityai/stable-diffusion-xl-base-1.0** (SDXL)
- Generate a **presentation-ready architecture image** in parallel with PlantUML
- Use the **same architectural understanding** for both outputs

---

## Core Architectural Principle (STRICT)

The system MUST follow this separation:

1. LLM acts as an **Architect**
2. Architecture Plan is the **single source of truth**
3. Renderers (PlantUML, SDXL) are **pure consumers**

The SDXL image generator must NEVER:
- Infer system structure
- Invent components
- Override architectural decisions

---

## Updated High-Level Workflow

Input (code or .docx)
  ↓
Text Extraction & Normalization
  ↓
LLM Call #1 — Architecture Reasoning
  ↓
Architecture Plan (JSON)
  ↓
├── LLM Call #2 — PlantUML Generator
├── LLM Call #3 — SDXL Prompt Generator
  ↓
PlantUML Renderer + Hugging Face SDXL Inference
  ↓
Final Output (Technical + Visual)

---

## Shared Architecture Plan Contract

The first LLM call MUST output a JSON structure like:

{
  "system_name": "string",
  "diagram_views": ["system_context", "container", "component", "sequence"],
  "zones": {
    "clients": [],
    "edge": [],
    "core_services": [],
    "external_services": [],
    "data_stores": []
  },
  "relationships": [
    {
      "from": "string",
      "to": "string",
      "type": "sync | async | data | auth",
      "description": "string"
    }
  ],
  "visual_hints": {
    "layout": "left-to-right | top-down",
    "group_by_zone": true,
    "external_dashed": true
  }
}

This JSON is immutable and reused for all renderers.

---

## LLM Call #1 — Architecture Reasoning Prompt

"""
You are a senior software architect.

Input:
<EXTRACTED CODE OR ARCHITECTURE TEXT FROM DOCX>

Your task:
1. Understand the system at an architectural level.
2. Decide which architectural diagram views are appropriate.
3. Identify system zones (clients, edge, core services, external services, data stores).
4. Identify relationships and interactions.
5. Output a structured Architecture Plan JSON.

Rules:
- Do NOT generate UML or PlantUML.
- Do NOT describe classes or methods.
- Think in terms of responsibilities and boundaries.
- Output ONLY valid JSON.
"""

---

## LLM Call #2 — PlantUML Generator

Input: Architecture Plan JSON

Prompt:
"""
You are a PlantUML diagram generator.

Using the following architecture plan JSON:
<ARCH_PLAN_JSON>

Generate one or more PlantUML diagrams.

Rules:
- Use C4-style or component/sequence diagrams where appropriate.
- Group components using boundaries.
- Avoid class diagrams unless explicitly required.
- Output valid PlantUML blocks only.
- Wrap each diagram in @startuml and @enduml.
"""

---

## LLM Call #3 — SDXL Prompt Generator

Input: SAME Architecture Plan JSON

Prompt:
"""
You are a technical visualization designer.

Using the following architecture plan JSON:
<ARCH_PLAN_JSON>

Generate a single detailed prompt suitable for Stable Diffusion XL
to render a clean software architecture diagram.

Prompt requirements:
- Describe grouped components and zones explicitly
- Describe arrows and data flow direction
- Specify white or light background
- Specify minimal, flat, professional technical style
- Emphasize readability and spacing
- Do NOT invent new components

Output ONLY the prompt text.
"""

---

## Hugging Face SDXL Integration

Model:
stabilityai/stable-diffusion-xl-base-1.0

Authentication:
- Use Hugging Face API token from `.env`
- Reuse existing env loading logic

.env example:
HF_API_TOKEN=hf_xxxxxxxxxxxxxxxxx

API Endpoint:
https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0

Implementation requirements:
- Send the SDXL prompt as input
- Receive image bytes
- Save image as PNG
- Handle model loading delay (retry if model is warming up)

---

## Output Contract

For each input file, return:

{
  "architecture_plan": {...},
  "plantuml": {
    "diagrams": [
      { "type": "component", "file": "component.png" },
      { "type": "sequence", "file": "sequence.png" }
    ]
  },
  "sdxl": {
    "prompt": "string",
    "image_file": "architecture_visual.png",
    "model": "stabilityai/stable-diffusion-xl-base-1.0"
  }
}

---

## Non-Goals (Strict)

- Do NOT generate images directly from raw code or doc text
- Do NOT let SDXL infer architecture
- Do NOT mix semantic diagram types
- Do NOT replace PlantUML with SDXL

---

## Code Organization

- architect_agent/
- plantuml_agent/
- sdxl_agent/
- renderers/
- api/
- cli/
- utils/

Renderer interface example:
render(architecture_plan, renderer_type)

---

## Documentation

- Explain why PlantUML is canonical
- Explain why SDXL is visual-only
- Provide example using NPM architecture .docx
- Document prompt structure and responsibilities

---

## Final Deliverables

- Updated architecture reasoning flow
- Hugging Face SDXL renderer module
- Example output (PlantUML + SDXL image)
- README explaining dual-renderer design