"""Visual Grammar maps semantic intent to concrete visuals."""
from __future__ import annotations

import re

from typing import Dict, List, Optional, Set, Tuple

from src.aesthetics.aesthetic_plan_schema import AestheticPlan
from src.aesthetics.style_transformer import HighlightSelection
from src.animation.svg_structural_analyzer import SVGStructuralGraph
from src.intent.semantic_aesthetic_ir import SemanticAestheticIR


def _normalize_key(value: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in (value or "").lower()).strip("_")


def _normalize_color_value(value: str) -> Optional[str]:
    if not value:
        return None
    token = value.strip()
    if token.startswith('#'):
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
    if token.lower().startswith('rgb'):
        match = re.match(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", token, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            r, g, b = (max(0, min(255, int(val))) for val in match.groups())
        except ValueError:
            return None
        return f"#{r:02X}{g:02X}{b:02X}"
    return None


def _extract_user_palette(intent: SemanticAestheticIR) -> List[str]:
    metadata = getattr(intent, "metadata", {}) or {}
    palette = metadata.get("userPalette")
    if not palette:
        return []
    if isinstance(palette, str):
        palette_values = [palette]
    elif isinstance(palette, list):
        palette_values = [str(entry) for entry in palette]
    else:
        return []
    normalized: List[str] = []
    for entry in palette_values:
        color = _normalize_color_value(entry)
        if color and color not in normalized:
            normalized.append(color)
    return normalized


def _palette_for_intent(intent: SemanticAestheticIR) -> Dict[str, Dict[str, str]]:
    mood = intent.globalIntent.mood
    contrast = intent.globalIntent.contrast

    base = {
        "background": "#ffffff",
        "node_fill": "#f1f5f9",
        "node_stroke": "#334155",
        "node_highlight_fill": "#e0f2fe",
        "node_highlight_stroke": "#0284c7",
        "edge": "#64748b",
        "edge_active": "#0ea5e9",
        "text": "#0f172a",
        "font_weight": "500",
    }

    if mood == "calm":
        base.update({
            "node_fill": "#ecfeff",
            "node_stroke": "#0e7490",
            "node_highlight_fill": "#cffafe",
            "node_highlight_stroke": "#0891b2",
            "edge_active": "#22d3ee",
        })
    elif mood == "vibrant":
        base.update({
            "node_fill": "#ffedd5",
            "node_stroke": "#f97316",
            "node_highlight_fill": "#fbcfe8",
            "node_highlight_stroke": "#ec4899",
            "edge_active": "#22c55e",
        })
    elif mood == "energetic":
        base.update({
            "node_fill": "#fee2e2",
            "node_stroke": "#ef4444",
            "node_highlight_fill": "#fecaca",
            "node_highlight_stroke": "#dc2626",
            "edge_active": "#f97316",
        })
    elif mood == "minimal":
        base.update({
            "node_fill": "#f8fafc",
            "node_stroke": "#475569",
            "edge_active": "#94a3b8",
        })

    if contrast == "low":
        base.update({
            "node_stroke": "#94a3b8",
            "edge": "#94a3b8",
            "edge_active": "#64748b",
            "font_weight": "400",
        })
    elif contrast == "high":
        base.update({
            "node_stroke": "#0f172a",
            "edge": "#0f172a",
            "edge_active": "#0ea5e9",
            "font_weight": "600",
        })

    user_palette = _extract_user_palette(intent)
    if user_palette:
        primary = user_palette[0]
        secondary = user_palette[1] if len(user_palette) > 1 else user_palette[0]
        base.update({
            "node_fill": primary,
            "node_stroke": secondary,
            "node_highlight_fill": secondary,
            "node_highlight_stroke": primary,
            "edge": secondary,
            "edge_active": secondary,
        })

    return base


def _map_highlights(intent: SemanticAestheticIR, graph: SVGStructuralGraph) -> HighlightSelection:
    node_ids: Set[str] = set()
    edge_ids: Set[str] = set()

    node_lookup = {}
    for node in graph.nodes:
        key = _normalize_key(node.label or node.id)
        if key:
            node_lookup[key] = node.id

    for key, node_intent in intent.nodeIntent.items():
        norm = _normalize_key(key)
        target = node_lookup.get(norm)
        if not target:
            continue
        if node_intent.importance == "primary" or node_intent.attention == "focus":
            node_ids.add(target)

    edge_lookup = {}
    for edge in graph.edges:
        src = _normalize_key(edge.source_id or "")
        tgt = _normalize_key(edge.target_id or "")
        if src and tgt:
            edge_lookup[f"{src}->{tgt}"] = edge.id

    for key, edge_intent in intent.edgeIntent.items():
        norm = _normalize_key(key)
        norm = norm.replace("__", "_")
        if "_to_" in norm:
            norm = norm.replace("_to_", "->")
        if "_" in norm and "->" not in norm and "-" in key:
            norm = norm.replace("_", "->", 1)
        target = edge_lookup.get(norm)
        if not target:
            continue
        if edge_intent.activity == "active" or edge_intent.criticality == "high":
            edge_ids.add(target)

    return HighlightSelection(node_ids=node_ids, edge_ids=edge_ids)


def build_aesthetic_plan(intent: SemanticAestheticIR, graph: SVGStructuralGraph) -> Tuple[AestheticPlan, HighlightSelection]:
    palette = _palette_for_intent(intent)
    plan = AestheticPlan.from_dict({
        "theme": "vibrant" if intent.globalIntent.mood == "vibrant" else "minimalist",
        "background": palette["background"],
        "nodeStyles": {
            "default": {
                "fill": palette["node_fill"],
                "stroke": palette["node_stroke"],
                "strokeWidth": 1.4,
            },
            "highlight": {
                "fill": palette["node_highlight_fill"],
                "stroke": palette["node_highlight_stroke"],
                "strokeWidth": 2.2,
            },
        },
        "edgeStyles": {
            "default": {
                "stroke": palette["edge"],
                "strokeWidth": 1.2,
            },
            "active": {
                "stroke": palette["edge_active"],
                "strokeWidth": 2.2,
            },
        },
        "font": {
            "family": "system-ui",
            "weight": palette["font_weight"],
        },
    })

    highlights = _map_highlights(intent, graph)
    return plan, highlights
