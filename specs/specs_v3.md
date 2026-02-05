# Build v3: Dual-Output Architecture Visualization System (PlantUML + DALL·E)

## Context
We already have a system that:
- Accepts source code and .docx architecture documents
- Uses OpenAI API to analyze the input
- Automatically decides which architectural/UML diagram type is appropriate
- Generates PlantUML text and renders diagrams

Now extend this system to ALSO generate a **visual diagram using DALL·E** in parallel.

The goal is:
- PlantUML = deterministic, technical, correct
- DALL·E = visually expressive, presentation-ready

Both outputs must come from the SAME architectural understanding, not independent hallucinations.

---

## Core Design Principle (IMPORTANT)
The LLM must first act as an **Architect**, not a diagram generator.

The system must:
1. Produce a **shared architectural plan**
2. Use that plan to generate:
   - PlantUML text
   - DALL·E prompt text

DO NOT generate DALL·E prompts directly from raw code or raw doc text.

---

## High-Level Workflow

Input (code or .docx)
  ↓
Text Extraction & Preprocessing
  ↓
LLM Call #1 — Architecture Reasoning
  ↓
Architecture Plan (structured JSON)
  ↓
├── LLM Call #2 — PlantUML Generator
├── LLM Call #3 — DALL·E Prompt Generator
  ↓
PlantUML Renderer + DALL·E Image Generator
  ↓
Final Output (Technical + Visual)

---

## Architecture Plan (Shared Contract)

The first LLM call MUST return a JSON object like:

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

This JSON is the SINGLE source of truth for both PlantUML and DALL·E generation.

---

## LLM Call #1 — Architecture Reasoning Prompt (Embed in Code)

"""
You are a senior software architect.

Input:
<EXTRACTED CODE OR ARCHITECTURE TEXT FROM DOCX>

Your task:
1. Understand the system at an architectural level.
2. Decide which diagram views are appropriate (system context, container, component, sequence).
3. Identify system zones (clients, edge, core services, external services, data stores).
4. Identify relationships and interactions.
5. Output a structured Architecture Plan JSON.

Rules:
- DO NOT output UML or PlantUML.
- DO NOT describe classes or methods.
- Think in terms of system boundaries and responsibilities.
- Output ONLY valid JSON.
"""

---

## LLM Call #2 — PlantUML Generator

Input: Architecture Plan JSON

Prompt:
"""
You are a PlantUML generator.

Using the following architecture plan JSON:
<ARCH_PLAN_JSON>

Generate one or more PlantUML diagrams.

Rules:
- Use appropriate diagram types (C4-style, component, sequence).
- Group elements using boundaries where applicable.
- Do NOT generate class diagrams unless explicitly required.
- Output valid PlantUML blocks only.
- Wrap each diagram in @startuml / @enduml.
"""

---

## LLM Call #3 — DALL·E Prompt Generator

Input: SAME Architecture Plan JSON

Prompt:
"""
You are a technical visualization designer.

Using the following architecture plan JSON:
<ARCH_PLAN_JSON>

Generate a single detailed DALL·E prompt that describes:
- System purpose
- Major components
- Grouping into zones
- Direction of data flow
- Visual style suitable for architecture diagrams

Rules:
- DO NOT invent components not in the plan.
- Focus on clarity, spacing, and hierarchy.
- Use terms like: 'architecture diagram', 'system diagram', 'grouped components', 'clean layout'.
- Output ONLY the prompt text, no JSON.
"""

---

## DALL·E Integration

- Use the same OpenAI API key already present in `.env`
- Generate one image per architecture plan
- Use neutral, professional style (white background, readable labels)
- Save image alongside PlantUML renders

---

## Output Structure

For each input file, return:

{
  "architecture_plan": {...},
  "plantuml": {
    "diagrams": [
      { "type": "component", "file": "component.png" },
      { "type": "sequence", "file": "sequence.png" }
    ]
  },
  "dalle": {
    "prompt": "string",
    "image_file": "architecture_visual.png"
  }
}

---

## Non-Goals (Strict)

- Do NOT mix UML types in one PlantUML diagram
- Do NOT generate DALL·E images without architecture plan
- Do NOT let DALL·E decide system structure
- Do NOT bypass PlantUML generation

---

## Documentation & Code Quality

- Modularize: architect_agent, plantuml_agent, dalle_agent
- Reuse existing OpenAI client & .env configuration
- Add comments explaining architectural decisions
- Provide example usage for .docx input

---

## Final Deliverables

- Updated folder structure
- New agents/modules for architecture reasoning & DALL·E
- Example run using NPM architecture doc
- README explaining dual-output philosophy