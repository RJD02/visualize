"""SVG-as-IR validator."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import List

ALLOWED_HEX_TOKENS = {
    "#0f172a",
    "#1e293b",
    "#334155",
    "#475569",
    "#64748b",
    "#94a3b8",
    "#e2e8f0",
    "#f8fafc",
}

ALLOWED_STYLE_PREFIXES = (
    "var(",
    "none",
    "currentColor",
)

GRAPHIC_TAGS = {
    "path",
    "rect",
    "text",
    "line",
    "circle",
    "ellipse",
    "polygon",
    "polyline",
}


class IRValidationError(ValueError):
    pass


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _has_hex_color(value: str) -> bool:
    return bool(re.search(r"#[0-9a-fA-F]{3,6}", value or ""))


def validate_svg_ir(svg_text: str) -> None:
    errors: List[str] = []
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as exc:
        raise IRValidationError(f"Invalid SVG XML: {exc}") from exc

    if _local_name(root.tag) != "svg":
        errors.append("Root element must be <svg>.")

    parent_map = {child: parent for parent in root.iter() for child in parent}

    for elem in root.iter():
        tag = _local_name(elem.tag)
        if tag in {"animate", "animateTransform", "set"}:
            errors.append("Animation elements are not allowed.")
        if "transform" in elem.attrib and "data-transform-reason" not in elem.attrib:
            errors.append(f"Transform without data-transform-reason on {tag}.")

        if tag == "g":
            if "id" not in elem.attrib:
                errors.append("<g> elements must have an id.")
            if "data-kind" not in elem.attrib:
                errors.append(f"<g id='{elem.attrib.get('id', '')}'> missing data-kind.")
            if "data-role" not in elem.attrib:
                errors.append(f"<g id='{elem.attrib.get('id', '')}'> missing data-role.")

        if tag in GRAPHIC_TAGS:
            parent = parent_map.get(elem)
            parent_tag = _local_name(parent.tag) if parent is not None else None
            if parent_tag != "g":
                errors.append(f"{tag} must be inside a <g> group.")
            if "id" not in elem.attrib:
                errors.append(f"{tag} elements must have an id.")

        for attr in ("fill", "stroke"):
            if attr in elem.attrib:
                value = elem.attrib[attr]
                if value and not value.startswith(ALLOWED_STYLE_PREFIXES):
                    if _has_hex_color(value):
                        if value.lower() not in ALLOWED_HEX_TOKENS:
                            errors.append(f"Disallowed hex color in {attr}: {value}")
                    else:
                        errors.append(f"Non-token color in {attr}: {value}")

        if tag == "style" and elem.text:
            if _has_hex_color(elem.text):
                for match in re.findall(r"#[0-9a-fA-F]{3,6}", elem.text):
                    if match.lower() not in ALLOWED_HEX_TOKENS:
                        errors.append(f"Disallowed hex color in style: {match}")
            if "@keyframes" in elem.text:
                errors.append("Inline CSS animations are not allowed.")

    if errors:
        raise IRValidationError("; ".join(errors))
