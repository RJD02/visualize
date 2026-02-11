"""Aesthetic Intelligence LLM - MCP tool for generating aesthetic plans."""
from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, Optional, Tuple


from src.animation.svg_structural_analyzer import SVGStructuralGraph, analyze_svg
from src.aesthetics.aesthetic_plan_schema import AestheticPlan
from src.mcp.registry import MCPTool, mcp_registry
from src.utils.config import settings
from src.utils.openai_client import get_openai_client


AESTHETIC_INTELLIGENCE_PROMPT = """You are a senior visual designer specialized in SVG diagram aesthetics.

Your task: analyze the diagram structure and propose an aesthetic plan that improves visual hierarchy and clarity.

ABSOLUTE CONSTRAINTS:
- You MUST NOT add or remove elements
- You MUST NOT alter labels or topology
- You MUST return ONLY JSON

INPUTS:
- structure_json: {structure_json}
- diagram_type: {diagram_type}
- diagram_size: {diagram_size}
- density_score: {density_score}
- animation_present: {animation_present}

OUTPUT FORMAT (STRICT):
{{
  "theme": "minimalist" | "high-contrast" | "vibrant",
  "background": "#ffffff",
  "nodeStyles": {{
    "default": {{ "fill": "#ffffff", "stroke": "#000000", "strokeWidth": 1 }},
    "highlight": {{ "fill": "#ffffff", "stroke": "#000000", "strokeWidth": 2 }}
  }},
  "edgeStyles": {{
    "default": {{ "stroke": "#000000", "strokeWidth": 1 }},
    "active": {{ "stroke": "#000000", "strokeWidth": 2 }}
  }},
  "font": {{
    "family": "system-ui",
    "weight": "normal"
  }}
}}

Return ONLY valid JSON. No prose, no CSS."""


def _generate_plan_id(svg_id: str, structure: Dict[str, Any]) -> str:
    content = json.dumps(structure, sort_keys=True)
    hash_val = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"plan-{svg_id}-{hash_val}"


def _call_llm(prompt: str) -> Optional[str]:
    if not settings.openai_api_key:
        return None
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=1200,
        )
        return response.choices[0].message.content
    except Exception as exc:
        print(f"LLM call failed: {exc}")
        return None


def _parse_llm_response(response: str) -> Optional[AestheticPlan]:
    try:
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        data = json.loads(cleaned)
        return AestheticPlan.from_dict(data)
    except Exception as exc:
        print(f"Failed to parse aesthetic plan: {exc}")
        return None


def _density_score(graph: SVGStructuralGraph) -> float:
    area = max(graph.width * graph.height, 1.0)
    return ((len(graph.nodes) + len(graph.edges)) / area) * 10000.0


def _fallback_palette(graph: SVGStructuralGraph) -> Tuple[str, Dict[str, Any]]:
    score = _density_score(graph)
    node_count = len(graph.nodes)
    if node_count <= 5:
        return "high-contrast", {
            "background": "#0f172a",
            "node_default": {"fill": "#1e293b", "stroke": "#f8fafc", "strokeWidth": 1.6},
            "node_highlight": {"fill": "#22d3ee", "stroke": "#67e8f9", "strokeWidth": 2.2},
            "edge_default": {"stroke": "#94a3b8", "strokeWidth": 1.4},
            "edge_active": {"stroke": "#f59e0b", "strokeWidth": 2.2},
            "font_weight": "600",
        }
    if score > 0.08 or node_count >= 18:
        return "minimalist", {
            "background": "#f8fafc",
            "node_default": {"fill": "#f1f5f9", "stroke": "#64748b", "strokeWidth": 1.2},
            "node_highlight": {"fill": "#e2e8f0", "stroke": "#0f172a", "strokeWidth": 2.0},
            "edge_default": {"stroke": "#94a3b8", "strokeWidth": 1.0},
            "edge_active": {"stroke": "#0ea5e9", "strokeWidth": 2.0},
            "font_weight": "500",
        }
    return "vibrant", {
        "background": "#ffffff",
        "node_default": {"fill": "#e0f2fe", "stroke": "#0ea5e9", "strokeWidth": 1.4},
        "node_highlight": {"fill": "#fef3c7", "stroke": "#f59e0b", "strokeWidth": 2.2},
        "edge_default": {"stroke": "#64748b", "strokeWidth": 1.2},
        "edge_active": {"stroke": "#f97316", "strokeWidth": 2.2},
        "font_weight": "500",
    }


def _fallback_plan(graph: SVGStructuralGraph) -> AestheticPlan:
    theme, palette = _fallback_palette(graph)
    data = {
        "theme": theme,
        "background": palette["background"],
        "nodeStyles": {
            "default": palette["node_default"],
            "highlight": palette["node_highlight"],
        },
        "edgeStyles": {
            "default": palette["edge_default"],
            "active": palette["edge_active"],
        },
        "font": {
            "family": "system-ui",
            "weight": palette["font_weight"],
        },
    }
    return AestheticPlan.from_dict(data)


def generate_aesthetic_plan_llm(
    svg_text: str,
    svg_id: str = "svg-1",
    animation_present: bool = False,
) -> AestheticPlan:
    graph = analyze_svg(svg_text, svg_id)
    structure = graph.to_dict()
    prompt = AESTHETIC_INTELLIGENCE_PROMPT.format(
        structure_json=json.dumps(structure, indent=2),
        diagram_type=graph.diagram_type,
        diagram_size=f"{graph.width}x{graph.height}",
        density_score=f"{_density_score(graph):.4f}",
        animation_present=str(animation_present).lower(),
    )

    llm_response = _call_llm(prompt)
    if llm_response:
        plan = _parse_llm_response(llm_response)
        if plan:
            return plan

    return _fallback_plan(graph)


def tool_aesthetic_planner(
    context: Dict[str, Any],
    svg_text: str,
    svg_id: str = "svg-1",
    animation_present: bool = False,
) -> Dict[str, Any]:
    try:
        plan = generate_aesthetic_plan_llm(svg_text, svg_id, animation_present)
        return {
            "success": True,
            "plan": plan.to_dict(),
            "plan_json": plan.to_json(),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "plan": None,
        }


AESTHETIC_INTELLIGENCE_TOOL = MCPTool(
    name="aesthetic_planner_llm",
    description="Analyze SVG structure and generate an aesthetic plan using LLM",
    input_schema={
        "type": "object",
        "properties": {
            "svg_text": {"type": "string", "description": "The SVG content to analyze"},
            "svg_id": {"type": "string", "description": "Unique identifier for the SVG", "default": "svg-1"},
            "animation_present": {"type": "boolean", "description": "Whether animation will be applied"},
        },
        "required": ["svg_text"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "plan": {"type": "object"},
            "plan_json": {"type": "string"},
            "error": {"type": "string"},
        },
    },
    side_effects="none",
    handler=tool_aesthetic_planner,
)


def register_aesthetic_tools() -> None:
    mcp_registry.register(AESTHETIC_INTELLIGENCE_TOOL)


register_aesthetic_tools()
