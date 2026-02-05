"""Aesthetic Plan Schema - Defines the structure of aesthetic plans."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict


THEME_CHOICES = {"minimalist", "high-contrast", "vibrant"}
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class StyleBlock:
    fill: str
    stroke: str
    strokeWidth: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fill": self.fill,
            "stroke": self.stroke,
            "strokeWidth": self.strokeWidth,
        }


@dataclass(frozen=True)
class FontBlock:
    family: str
    weight: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "family": self.family,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class AestheticPlan:
    theme: str
    background: str
    nodeStyles: Dict[str, StyleBlock]
    edgeStyles: Dict[str, StyleBlock]
    font: FontBlock

    def to_dict(self) -> Dict[str, Any]:
        return {
            "theme": self.theme,
            "background": self.background,
            "nodeStyles": {k: v.to_dict() for k, v in self.nodeStyles.items()},
            "edgeStyles": {k: v.to_dict() for k, v in self.edgeStyles.items()},
            "font": self.font.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AestheticPlan":
        theme = (data or {}).get("theme")
        if theme not in THEME_CHOICES:
            raise ValueError("Invalid theme")
        background = (data or {}).get("background") or ""
        if not HEX_COLOR_RE.match(background):
            raise ValueError("Invalid background color")
        node_styles = (data or {}).get("nodeStyles") or {}
        edge_styles = (data or {}).get("edgeStyles") or {}
        font = (data or {}).get("font") or {}

        def _style_block(value: Dict[str, Any], allow_missing_fill: bool = False) -> StyleBlock:
            fill = value.get("fill") or ""
            stroke = value.get("stroke") or ""
            stroke_width = value.get("strokeWidth")
            if allow_missing_fill and not fill:
                fill = "#000000"
            if not HEX_COLOR_RE.match(fill) or not HEX_COLOR_RE.match(stroke):
                raise ValueError("Invalid color in style block")
            if stroke_width is None:
                raise ValueError("Missing strokeWidth in style block")
            try:
                stroke_width = float(stroke_width)
            except (ValueError, TypeError) as exc:
                raise ValueError("Invalid strokeWidth in style block") from exc
            return StyleBlock(fill=fill, stroke=stroke, strokeWidth=stroke_width)

        default_node = _style_block(node_styles.get("default") or {})
        highlight_node = _style_block(node_styles.get("highlight") or {})
        default_edge = _style_block(edge_styles.get("default") or {}, allow_missing_fill=True)
        active_edge = _style_block(edge_styles.get("active") or {}, allow_missing_fill=True)

        family = font.get("family") or "system-ui"
        weight = font.get("weight") or "normal"
        return cls(
            theme=theme,
            background=background,
            nodeStyles={
                "default": default_node,
                "highlight": highlight_node,
            },
            edgeStyles={
                "default": default_edge,
                "active": active_edge,
            },
            font=FontBlock(family=family, weight=weight),
        )
