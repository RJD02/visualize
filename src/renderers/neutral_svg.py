"""Neutral SVG enforcement for renderer outputs."""
from __future__ import annotations

import re
from typing import Iterable
from xml.etree import ElementTree as ET


_COLOR_PATTERN = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})|rgba?\(|hsla?\(|\b(?:red|blue|green|yellow|orange|purple|pink|teal|cyan|magenta|black|white|gray|grey|brown|gold|silver)\b")


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def strip_svg_colors(svg_text: str) -> str:
    root = ET.fromstring(svg_text)
    for el in list(root.iter()):
        tag = _strip_ns(el.tag)
        if tag == "style":
            parent = _find_parent(root, el)
            if parent is not None:
                parent.remove(el)
            continue
        for attr in ("fill", "stroke", "color"):
            if attr in el.attrib:
                value = el.attrib.get(attr, "")
                if _COLOR_PATTERN.search(value):
                    el.attrib.pop(attr, None)
        if "style" in el.attrib:
            value = el.attrib.get("style", "")
            if _COLOR_PATTERN.search(value):
                el.attrib.pop("style", None)
    return ET.tostring(root, encoding="unicode")


def _find_parent(root: ET.Element, target: ET.Element) -> ET.Element | None:
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                return parent
    return None


def _iter_style_text(root: ET.Element) -> Iterable[str]:
    for el in root.iter():
        if _strip_ns(el.tag) == "style" and el.text:
            yield el.text


def validate_neutral_svg(svg_text: str) -> None:
    root = ET.fromstring(svg_text)
    for el in root.iter():
        if _strip_ns(el.tag) == "style" and el.text and _COLOR_PATTERN.search(el.text):
            raise ValueError("Inline style colors are not allowed.")
        for attr in ("fill", "stroke", "color", "style"):
            if attr in el.attrib and _COLOR_PATTERN.search(el.attrib.get(attr, "")):
                raise ValueError("Inline colors are not allowed.")
    for style_text in _iter_style_text(root):
        if _COLOR_PATTERN.search(style_text):
            raise ValueError("Style tag contains colors.")
