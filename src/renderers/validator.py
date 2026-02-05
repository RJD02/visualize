"""Validate neutral SVG: ensure no inline styles/colors or style tags."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Tuple


def validate_neutral_svg(svg_text: str) -> Tuple[bool, str]:
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as e:
        return False, f"Invalid SVG: {e}"

    # Fail if there are any <style> elements
    for style in root.findall('.//{http://www.w3.org/2000/svg}style'):
        return False, "SVG contains <style> tags"

    # Also check for inline fill/stroke attributes on any element
    for elem in root.iter():
        for attr in ("fill", "stroke", "style"):
            val = elem.attrib.get(attr)
            if val:
                # If style attribute contains 'fill' or colors, fail
                if attr in ("fill", "stroke") and val.strip() and val.strip().lower() not in ("none",):
                    return False, f"SVG contains non-neutral attribute {attr}={val}"
                if attr == "style" and ("fill:" in val or "stroke:" in val or "color:" in val):
                    return False, "SVG contains style attribute with colors"

    return True, "OK"
