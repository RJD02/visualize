## IR Enrichment Prompt (v34)

Purpose
-------
This prompt is intended for a Codex-style agent that receives a minimal IR (Intermediate Representation) JSON describing an architecture plan and enriches it with detailed structural and styling metadata so renderers (PlantUML, Mermaid, SVG) can draw fully-styled diagrams.

Instructions for the agent
--------------------------
You are given a JSON object that represents a minimal architecture IR. Your task is to produce a single enriched JSON object (no explanatory text) that contains complete node and edge descriptions, styling intents, rendering hints, and metadata.

Input
- A JSON object containing at least: `system_name`, `zones`, `relationships`, `diagram_views`, and optional `visual_hints` or `aesthetic_intent`.

Rules
- Preserve any existing IDs or labels when present.
- Do not invent unrelated systems; derive nodes primarily from `zones` and `relationships`. If a relationship references an unnamed node, create a node with a normalized `node_id` derived from the label.
- Normalize all IDs to alphanumeric + underscore (lowercase) for renderer compatibility.
- Add per-node and per-edge `confidence` (0-1) and a `reason` string briefly describing the inference source.
- Ensure every node object has these fields:
  - `node_id` (string)
  - `label` (string)
  - `role` (e.g., "system", "container", "component", "actor")
  - `zone` (one of the zone keys or null)
  - `type` (one of: `system`, `container`, `component`, `data_store`, `external`)
  - `stereotype` (optional short label)
  - `shape` (one of: `rectangle`, `rounded`, `circular`, `cylinder`, `cloud`)
  - `size_hint` (e.g., `small|medium|large`) or explicit `width`/`height`
  - `node_style` (object): `fillColor`, `borderColor`, `textColor`, `borderWidth`, `fontSize`, `fontFamily`, `padding`
  - `rendering_hints` (object) with `plantuml` and `mermaid` sub-keys describing renderer-specific types (e.g., `plantuml_shape`, `mermaid_type`)
  - `metadata` (object) for provenance and extracted attributes

- Ensure every edge object has these fields:
  - `edge_id` (string)
  - `from_id` and `to_id` (normalized node_ids)
  - `rel_type` (e.g., `sync`, `async`, `data`, `depends`)
  - `label` (string)
  - `style` (e.g., `solid`, `dashed`, `dotted`)
  - `color`, `width` (px), `arrowhead` (e.g., `normal`, `open`, `none`)
  - `text_style` (object): `fontSize`, `fontFamily`, `textColor`
  - `curvature` (number, optional)
  - `confidence` and `reason`

- Add `nodeIntent`, `edgeIntent`, and `globalIntent` to reflect styling choices:
  - `nodeIntent` can provide defaults by role (e.g., containers default to rounded rectangles)
  - `edgeIntent` maps `rel_type` to default styles (e.g., `async` -> dashed orange)
  - `globalIntent` should include `palette` (use provided `aesthetic_intent.userPalette` if present), `layout`, `density`, `mood`

- Output should include top-level keys:
  - `diagram_type` (copy from input or default to `diagram`)
  - `layout` (e.g., `top-down`, `left-right`)
  - `zone_order` (array of zone keys)
  - `nodes` (array of enriched nodes)
  - `edges` (array of enriched edges)
  - `nodeIntent`, `edgeIntent`, `globalIntent`
  - `metadata` with `generated_by`, `spec_version` ("v34"), `timestamp` (ISO8601)

Mapping to user aesthetic intent
- If `aesthetic_intent.userPalette` exists, map the first color to primary node fills, second to accents/backgrounds, and produce a 5-color derived palette for borders, stroke, and text contrast. Respect `globalIntent.mood` (e.g., `minimal` -> low contrast, simple shapes) and `density` (e.g., `compact` -> smaller size hints and tighter spacing).

Renderer compatibility
- Ensure the enriched IR contains renderer-friendly hints:
  - For PlantUML: `plantuml_shape` (component/class/interface/cloud/actor), `plantuml_color` (hex), and `plantuml_label` (escaped)
  - For Mermaid: `mermaid_type` (class, subgraph, entity), and sanitized `node_id` suitable for Mermaid

Validation and confidence
- Where inferred (e.g., node zone from relationships), set `confidence` to 0.6-0.9 depending on inference strength; where present in input, set confidence 1.0.
- Include a short `validation` array in `metadata` listing any assumptions or missing data that were inferred.

Example enriched node (illustrative)
```
{
  "node_id": "zip_file_processor",
  "label": "Zip File Processor",
  "role": "container",
  "zone": "core_services",
  "type": "container",
  "stereotype": "processor",
  "shape": "rounded",
  "size_hint": "medium",
  "node_style": {
    "fillColor": "#FF6B81",
    "borderColor": "#CC5168",
    "textColor": "#FFFFFF",
    "borderWidth": 2,
    "fontSize": 12,
    "fontFamily": "Inter, Arial, sans-serif",
    "padding": 8
  },
  "rendering_hints": {
    "plantuml": { "plantuml_shape": "component", "plantuml_color": "#FF6B81" },
    "mermaid": { "mermaid_type": "class" }
  },
  "metadata": { "confidence": 0.95, "reason": "Explicit in zones" }
}
```

Example enriched edge (illustrative)
```
{
  "edge_id": "user_ui__to__api_gateway",
  "from_id": "user_interface",
  "to_id": "api_gateway",
  "rel_type": "sync",
  "label": "User uploads zip file",
  "style": "solid",
  "color": "#333333",
  "width": 2,
  "arrowhead": "normal",
  "text_style": { "fontSize": 11, "fontFamily": "Inter", "textColor": "#333333" },
  "curvature": 0,
  "confidence": 0.9,
  "reason": "Explicit relationship in plan"
}
```

Final output constraints
- Return the enriched JSON only (no commentary, no wrapper text). Ensure valid JSON.

Usage
-----
Feed this prompt to your Codex/LLM agent along with the original IR JSON as `INPUT_IR` and request `OUTPUT_JSON`.

Spec metadata
- spec_version: v34
- filename: specs_v34_ir_enrichment_prompt.md

## Concrete Gaps / Current Symptoms

- Missing node details: many IRs only include labels or zone names but not full node objects with `node_id`, `role`, `type`, `shape`, `size_hint`, `node_style`, or `rendering_hints`. Renderers therefore can't select shapes, fonts, or colors.
- Missing edge details: edges are often only descriptive text; missing `edge_id`, `from_id`/`to_id` normalization, `rel_type`, `style`, `color`, `width`, `arrowhead`, and `text_style` prevent consistent rendering.
- No renderer hints: `plantuml` / `mermaid` specific hints are absent; PlantUML/mermaid adapters must guess shapes and labels, producing inconsistent diagrams.
- Aesthetic intent not propagated: user `aesthetic_intent` / `userPalette` is not translated into concrete `node_style`/`edge` styles (fill/border/text), so user choices are lost.
- No provenance / confidence: IR lacks `metadata` with `confidence` and `reason` fields; difficult to surface assumptions to users and to validate programmatically.
- ID normalization problems: node labels are used as IDs without sanitization; Mermaid/PlantUML may choke on spaces/special chars.
- SVG vs IR mismatch: `diagram_ir_versions.svg_text` may contain sufficient visual info, but `ir_json` is too sparse for programmatic edits or re-rendering with different styles.
- Missing validation & warnings: no consistent validation step flags missing or ambiguous items (e.g., relationships without nodes), so downstream steps fail silently.

## Implementation Plan (high level)

Goal: enrich minimal IRs into a rich, renderer-friendly IR that contains structured nodes/edges, styling intent, renderer hints, provenance/confidence, and validation metadata; integrate enrichment into ingestion and planning flows so generated diagrams are consistent with user aesthetic choices.

1) Define enriched IR JSON Schema
  - Deliverable: `specs/ir_enriched_schema_v1.json` (and examples in `specs/`)
  - Fields: top-level (`diagram_type`, `layout`, `zone_order`, `nodes`, `edges`, `nodeIntent`, `edgeIntent`, `globalIntent`, `metadata`)
  - Acceptance: a JSON Schema file plus at least two example enriched IRs (one system/context+container, one with sequence edges).

2) Refine prompt & build test harness
  - Update existing prompt (`specs_v34_ir_enrichment_prompt.md`) as needed (done).
  - Create `scripts/enrich_ir.py` that reads an input IR JSON, calls the LLM using the prompt, validates the output against the schema, and writes `outputs/<session>_ir_enriched.json`.
  - Acceptance: harness runs locally with environment LLM creds and produces a schema-valid enriched IR for the provided sample.

3) Implement enrichment service wrapper
  - Add `src/tools/ir_enricher.py` with functions: `enrich_ir(input_ir: dict) -> dict` and `validate_enriched_ir(ir: dict) -> list[str]` (returns validation errors).
  - Responsibilities: normalization of IDs, default `nodeIntent`/`edgeIntent` derivation from `aesthetic_intent`, confidence heuristics, timestamp/provenance, and fallbacks for missing data.
  - Acceptance: unit tests that assert normalized IDs, derived `node_style` from palette, and presence of required fields.

4) Integrate into pipeline
  - Call `enrich_ir(...)` from `ingest_input` and `handle_message` when a new plan/IR is created (before `_create_ir_version`), store enriched IR in `DiagramIR.ir_json` and also in `architecture_plans.data` when appropriate.
  - Add `enricher` as optional step controlled by `settings.enable_ir_enrichment` to allow rollback.
  - Acceptance: diagrams generated after integration reflect enriched attributes (shapes/colors/fonts) and `diagram_ir_versions.ir_json` contains the enriched object.

5) Update renderers
  - Modify PlantUML and Mermaid rendering adapters to prefer `rendering_hints` and `node_style` when composing PlantUML/Mermaid sources or SVG post-processing.
  - Ensure PlantUML escapes labels and uses `plantuml_color`/`plantuml_shape` hints.
  - Acceptance: same input IR rendered into visuals that match `globalIntent.palette` and node shapes.

6) Validation, tests & CI
  - Add schema validation unit tests and integration tests that run `scripts/enrich_ir.py` on sample IRs and verify successful render to PNG/SVG.
  - Add a linter/validator that flags low-confidence inferences for human review.
  - Acceptance: CI pipeline includes these tests and fails on schema or renderer regressions.

7) UI & human-in-the-loop
  - Add API/UI endpoints to preview enriched IR, show `metadata.validation` and confidence, and accept/reject the enriched IR before committing to DB.
  - Record decisions in `styling_audits` with `mode` and provenance.
  - Acceptance: front-end can fetch `/sessions/{id}/ir/enriched/preview` and commit accepted IR.

8) Monitoring, migration & DB notes
  - No DB schema changes necessary because `DiagramIR.ir_json` exists. Consider adding index on `diagram_ir_versions(session_id)` for retrieval speed.
  - Add logging for enrichment success/failure and a metric for enrichment coverage.
  - Acceptance: metrics show enrichment success rate and logged failures for investigation.

## Next steps (short term)
- Create `specs/ir_enriched_schema_v1.json` and example enriched IRs (priority).
- Scaffold `scripts/enrich_ir.py` and a minimal `src/tools/ir_enricher.py` (POC) to validate the flow.
- Run the POC on the attached sample IR and iterate until renderers produce acceptable visuals.

