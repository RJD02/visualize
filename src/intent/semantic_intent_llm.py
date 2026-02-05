"""Semantic Intent LLM - produces Semantic Aesthetic IR (no visuals)."""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from src.animation.svg_structural_analyzer import analyze_svg
from src.intent.semantic_aesthetic_ir import SemanticAestheticIR
from src.mcp.registry import MCPTool, mcp_registry
from src.utils.config import settings


SEMANTIC_INTENT_PROMPT = """You are a semantic intent planner for diagram visuals.

Return ONLY JSON matching this schema:
{
  "globalIntent": {
    "mood": "minimal|vibrant|calm|energetic",
    "contrast": "low|medium|high",
    "density": "compact|spacious"
  },
  "nodeIntent": {
    "<node_key>": {
      "importance": "primary|secondary|neutral",
      "attention": "focus|normal|deemphasize",
      "stability": "stable|dynamic|neutral"
    }
  },
  "edgeIntent": {
    "<edge_key>": {
      "activity": "active|passive|neutral",
      "criticality": "high|medium|low|neutral"
    }
  }
}

Rules:
- Do NOT output any colors, CSS, or animation names.
- Use node_key/edge_key from the provided structure list.
- If none apply, leave nodeIntent/edgeIntent empty.

User request:
{message}

Available nodes:
{nodes}

Available edges:
{edges}
"""


COLOR_WORDS = {
    "red", "blue", "green", "yellow", "orange", "purple", "pink", "teal", "cyan", "magenta",
    "black", "white", "gray", "grey", "brown", "gold", "silver",
}


def _sanitize_message(text: str) -> Tuple[str, bool]:
    lowered = (text or "").lower()
    has_color = any(word in lowered for word in COLOR_WORDS) or bool(re.search(r"#[0-9a-fA-F]{3,6}", text or ""))
    cleaned = re.sub(r"#[0-9a-fA-F]{3,6}", "", text or "")
    for word in COLOR_WORDS:
        cleaned = re.sub(rf"\b{re.escape(word)}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, has_color


def _infer_global_intent(text: str) -> Dict[str, str]:
    lowered = (text or "").lower()
    mood = "minimal"
    if any(tok in lowered for tok in ["calm", "quiet", "subtle", "soft"]):
        mood = "calm"
    elif any(tok in lowered for tok in ["vibrant", "bold", "lively"]):
        mood = "vibrant"
    elif any(tok in lowered for tok in ["energetic", "dynamic", "punchy"]):
        mood = "energetic"

    contrast = "medium"
    if any(tok in lowered for tok in ["low contrast", "gentle", "muted"]):
        contrast = "low"
    elif any(tok in lowered for tok in ["high contrast", "emphasize", "highlight"]):
        contrast = "high"

    density = "compact"
    if any(tok in lowered for tok in ["spacious", "airy", "roomy"]):
        density = "spacious"
    return {"mood": mood, "contrast": contrast, "density": density}


def _default_intent() -> SemanticAestheticIR:
    return SemanticAestheticIR()


def _call_llm(message: str, nodes: List[str], edges: List[str]) -> Optional[SemanticAestheticIR]:
    if not settings.openai_api_key:
        return None
    try:
        client = OpenAI(api_key=settings.openai_api_key)
        prompt = SEMANTIC_INTENT_PROMPT.format(
            message=message,
            nodes=json.dumps(nodes, indent=2),
            edges=json.dumps(edges, indent=2),
        )
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        raw = response.choices[0].message.content or "{}"
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        data = json.loads(match.group(0))
        return SemanticAestheticIR.from_dict(data)
    except Exception:
        return None


def generate_semantic_intent(svg_text: str, message: str) -> Tuple[SemanticAestheticIR, bool]:
    cleaned, had_color = _sanitize_message(message)
    graph = analyze_svg(svg_text, "semantic-intent")

    nodes = []
    for node in graph.nodes:
        key = (node.label or node.id or "").strip()
        if key:
            nodes.append(key)
    edges = []
    for edge in graph.edges:
        src = edge.source_id or ""
        tgt = edge.target_id or ""
        edges.append(f"{src}->{tgt}".strip("-"))

    llm_result = _call_llm(cleaned, nodes, edges)
    if llm_result:
        return llm_result, had_color

    global_intent = _infer_global_intent(cleaned)
    ir = SemanticAestheticIR.from_dict({"globalIntent": global_intent})
    return ir, had_color


def tool_semantic_intent_llm(
    context: Dict[str, object],
    svg_text: str,
    message: str,
) -> Dict[str, object]:
    intent, had_color = generate_semantic_intent(svg_text, message)
    return {
        "success": True,
        "intent": intent.to_dict(),
        "ignored_color_instructions": had_color,
    }


SEMANTIC_INTENT_TOOL = MCPTool(
    name="semantic_intent_llm",
    description="Generate semantic visual intent IR from user message and SVG structure.",
    input_schema={
        "type": "object",
        "properties": {
            "svg_text": {"type": "string"},
            "message": {"type": "string"},
        },
        "required": ["svg_text", "message"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "intent": {"type": "object"},
            "ignored_color_instructions": {"type": "boolean"},
        },
    },
    side_effects="none",
    handler=tool_semantic_intent_llm,
)


def register_semantic_intent_tool() -> None:
    mcp_registry.register(SEMANTIC_INTENT_TOOL)


register_semantic_intent_tool()
