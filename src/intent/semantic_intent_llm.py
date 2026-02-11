"""Semantic Intent LLM - produces Semantic Aesthetic IR (no visuals)."""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple


from src.animation.svg_structural_analyzer import analyze_svg
from src.intent.semantic_aesthetic_ir import SemanticAestheticIR
from src.mcp.registry import MCPTool, mcp_registry
from src.utils.config import settings
from src.utils.openai_client import get_openai_client


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


COLOR_NAME_MAP = {
    "red": "#FF3B30",
    "maroon": "#B03060",
    "crimson": "#DC143C",
    "blue": "#2196F3",
    "navy": "#001F54",
    "azure": "#007FFF",
    "cyan": "#00BCD4",
    "teal": "#008080",
    "turquoise": "#40E0D0",
    "green": "#34C759",
    "emerald": "#2ED573",
    "lime": "#A3E635",
    "yellow": "#FACC15",
    "gold": "#FBBF24",
    "orange": "#FFA500",
    "amber": "#FFB300",
    "brown": "#8B4513",
    "purple": "#A855F7",
    "violet": "#8A2BE2",
    "magenta": "#FF2D55",
    "pink": "#FF6B81",
    "black": "#111111",
    "white": "#FFFFFF",
    "gray": "#9CA3AF",
    "grey": "#9CA3AF",
    "silver": "#C0C0C0",
}

COLOR_WORDS = set(COLOR_NAME_MAP.keys())

_COLOR_WORD_PATTERN = "|".join(sorted(COLOR_WORDS, key=len, reverse=True))
_COLOR_REGEX = re.compile(
    rf"#(?:[0-9a-fA-F]{{3}}|[0-9a-fA-F]{{6}})\b|rgb\(\s*\d{{1,3}}\s*,\s*\d{{1,3}}\s*,\s*\d{{1,3}}\s*\)|\b(?:{_COLOR_WORD_PATTERN})\b",
    re.IGNORECASE,
)


def _normalize_hex(token: str) -> Optional[str]:
    raw = token.lstrip('#')
    if len(raw) == 3:
        raw = ''.join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return None
    try:
        int(raw, 16)
    except ValueError:
        return None
    return f"#{raw.upper()}"


def _normalize_rgb(token: str) -> Optional[str]:
    match = re.match(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", token, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        r, g, b = (max(0, min(255, int(val))) for val in match.groups())
    except ValueError:
        return None
    return f"#{r:02X}{g:02X}{b:02X}"


def _sanitize_message(text: str) -> Tuple[str, List[str]]:
    palette: List[str] = []

    def _push(value: Optional[str]) -> None:
        if value and value not in palette:
            palette.append(value)

    original = text or ""
    for match in _COLOR_REGEX.finditer(original):
        token = match.group(0)
        normalized: Optional[str] = None
        if token.startswith('#'):
            normalized = _normalize_hex(token)
        elif token.lower().startswith('rgb'):
            normalized = _normalize_rgb(token)
        else:
            normalized = COLOR_NAME_MAP.get(token.lower())
        _push(normalized)

    cleaned = _COLOR_REGEX.sub(' ', original)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned, palette


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
        client = get_openai_client()
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
    cleaned, palette = _sanitize_message(message)
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
        if palette:
            llm_result.metadata = dict(llm_result.metadata or {})
            llm_result.metadata["userPalette"] = palette
        return llm_result, bool(palette)

    global_intent = _infer_global_intent(cleaned)
    ir = SemanticAestheticIR.from_dict({"globalIntent": global_intent})
    if palette:
        ir.metadata = dict(ir.metadata or {})
        ir.metadata["userPalette"] = palette
    return ir, bool(palette)


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
