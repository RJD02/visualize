"""Parse PlantUML SVGs to identify nodes and edges for animation planning."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple
import re
from xml.etree import ElementTree as ET
import logging

logger = logging.getLogger(__name__)

STEP_RE = re.compile(r"\bstep\s*(\d+)\b", re.IGNORECASE)
# Valid CSS ID selector: starts with letter, followed by letters, digits, hyphens, underscores
VALID_CSS_ID_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")


def _is_valid_css_id(id_str: str) -> bool:
    """Check if a string is a valid CSS ID selector (no spaces, special chars)."""
    if not id_str:
        return False
    return bool(VALID_CSS_ID_RE.match(id_str))


def _sanitize_id_for_css(id_str: str) -> str:
    """Convert an invalid ID to a valid CSS-safe class name."""
    if not id_str:
        return ""
    # Replace spaces and special chars with hyphens
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", id_str)
    # Ensure starts with letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = "el-" + sanitized
    return sanitized


@dataclass
class NodeInfo:
    """Represents a node-like element in the SVG."""
    element: ET.Element
    label: str
    center: Tuple[float, float]
    step: Optional[int]
    anim_id: str
    selector: str


@dataclass
class EdgeInfo:
    """Represents an edge-like element in the SVG."""
    element: ET.Element
    center: Tuple[float, float]
    anim_id: str
    selector: str


@dataclass
class ParsedSvg:
    root: ET.Element
    nodes: List[NodeInfo]
    edges: List[EdgeInfo]


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _iter_descendants(el: ET.Element, tag: str) -> Iterable[ET.Element]:
    for child in el.iter():
        if _strip_ns(child.tag) == tag:
            yield child


def _text_from_element(el: ET.Element) -> str:
    text = "".join([t for t in el.itertext() if t]).strip()
    return text


def _parse_float(value: Optional[str], default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _center_from_rect(rect: ET.Element) -> Tuple[float, float]:
    x = _parse_float(rect.get("x"))
    y = _parse_float(rect.get("y"))
    w = _parse_float(rect.get("width"))
    h = _parse_float(rect.get("height"))
    return (x + w / 2, y + h / 2)


def _center_from_circle(circle: ET.Element) -> Tuple[float, float]:
    cx = _parse_float(circle.get("cx"))
    cy = _parse_float(circle.get("cy"))
    return (cx, cy)


def _center_from_ellipse(ellipse: ET.Element) -> Tuple[float, float]:
    cx = _parse_float(ellipse.get("cx"))
    cy = _parse_float(ellipse.get("cy"))
    return (cx, cy)


def _center_from_text(text_el: ET.Element) -> Tuple[float, float]:
    x = _parse_float(text_el.get("x"))
    y = _parse_float(text_el.get("y"))
    return (x, y)


def _center_from_path(path_el: ET.Element) -> Tuple[float, float]:
    d = path_el.get("d") or ""
    match = re.search(r"[Mm]\s*([\-\d\.]+)[,\s]+([\-\d\.]+)", d)
    if match:
        return (float(match.group(1)), float(match.group(2)))
    return (0.0, 0.0)


def _extract_step(label: str) -> Optional[int]:
    match = STEP_RE.search(label or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _find_node_candidates(root: ET.Element) -> List[ET.Element]:
    nodes: List[ET.Element] = []
    for el in root.iter():
        if _strip_ns(el.tag) != "g":
            continue
        if list(_iter_descendants(el, "title")) or list(_iter_descendants(el, "text")):
            nodes.append(el)
    return nodes


def _node_label(el: ET.Element) -> str:
    title_el = next(iter(_iter_descendants(el, "title")), None)
    if title_el is not None:
        text = _text_from_element(title_el)
        if text:
            return text
    text_el = next(iter(_iter_descendants(el, "text")), None)
    if text_el is not None:
        text = _text_from_element(text_el)
        if text:
            return text
    return ""


def _node_center(el: ET.Element) -> Tuple[float, float]:
    rect_el = next(iter(_iter_descendants(el, "rect")), None)
    if rect_el is not None:
        return _center_from_rect(rect_el)
    circle_el = next(iter(_iter_descendants(el, "circle")), None)
    if circle_el is not None:
        return _center_from_circle(circle_el)
    ellipse_el = next(iter(_iter_descendants(el, "ellipse")), None)
    if ellipse_el is not None:
        return _center_from_ellipse(ellipse_el)
    text_el = next(iter(_iter_descendants(el, "text")), None)
    if text_el is not None:
        return _center_from_text(text_el)
    return (0.0, 0.0)


def _is_descendant_of_any(el: ET.Element, candidates: List[ET.Element]) -> bool:
    for node in candidates:
        if el is node:
            continue
        for child in node.iter():
            if child is el:
                return True
    return False


def _make_valid_selector(el: ET.Element, fallback: str) -> Tuple[str, bool]:
    """
    Create a valid CSS selector for an element.
    
    Returns (selector, is_valid) where is_valid indicates if original ID was usable.
    For invalid IDs, adds a class to the element and returns class selector.
    """
    el_id = el.get("id")
    
    if el_id and _is_valid_css_id(el_id):
        # ID is valid - use it directly
        return f"#{el_id}", True
    
    if el_id:
        # ID exists but invalid (e.g., "Web Browser-to-API Gateway")
        # Log warning and use a sanitized class
        logger.warning(f"Invalid CSS ID '{el_id}' - contains spaces or special chars. Using class selector.")
        safe_class = _sanitize_id_for_css(el_id)
    else:
        # No ID at all - use fallback
        safe_class = fallback
    
    # Add the class to the element so the selector will work
    existing_class = el.get("class") or ""
    if safe_class not in existing_class.split():
        el.set("class", f"{existing_class} {safe_class}".strip())
    
    return f".{safe_class}", False


def _find_plantuml_entities(root: ET.Element) -> List[ET.Element]:
    """Find PlantUML entity elements (nodes) - they have class='entity' or class='cluster'."""
    entities = []
    for el in root.iter():
        if _strip_ns(el.tag) != "g":
            continue
        el_class = el.get("class") or ""
        if "entity" in el_class or "cluster" in el_class:
            entities.append(el)
    return entities


def _find_plantuml_links(root: ET.Element) -> List[ET.Element]:
    """Find PlantUML link elements (edges) - they have class='link'."""
    links = []
    for el in root.iter():
        if _strip_ns(el.tag) != "g":
            continue
        el_class = el.get("class") or ""
        if "link" in el_class:
            links.append(el)
    return links


def _is_plantuml_svg(root: ET.Element) -> bool:
    """Check if SVG was generated by PlantUML."""
    # PlantUML SVGs have <?plantuml ...?> or specific patterns
    for el in root.iter():
        el_class = el.get("class") or ""
        if "entity" in el_class or "link" in el_class or "cluster" in el_class:
            return True
    return False


def parse_svg(svg_text: str) -> ParsedSvg:
    """Parse SVG text into node/edge candidates with deterministic ordering metadata.
    
    Handles both PlantUML-generated SVGs (with ent*/lnk* IDs) and custom SVGs.
    Ensures all selectors are valid CSS selectors.
    """
    root = ET.fromstring(svg_text)
    
    # Check if this is a PlantUML SVG
    is_plantuml = _is_plantuml_svg(root)
    
    nodes: List[NodeInfo] = []
    edges: List[EdgeInfo] = []
    
    if is_plantuml:
        # PlantUML parsing - use entity/link classes
        entities = _find_plantuml_entities(root)
        for idx, el in enumerate(entities):
            label = _node_label(el)
            step = _extract_step(label)
            center = _node_center(el)
            fallback = f"anim-node-{idx + 1}"
            selector, _ = _make_valid_selector(el, fallback)
            nodes.append(NodeInfo(
                element=el, label=label, center=center, step=step,
                anim_id=f"node-{idx + 1}", selector=selector
            ))
        
        links = _find_plantuml_links(root)
        for idx, el in enumerate(links):
            # For PlantUML links, the <g class="link"> is the animatable element
            center = _node_center(el)  # Uses any rect/path inside
            fallback = f"anim-edge-{idx + 1}"
            selector, _ = _make_valid_selector(el, fallback)
            edges.append(EdgeInfo(
                element=el, center=center,
                anim_id=f"edge-{idx + 1}", selector=selector
            ))
    else:
        # Generic SVG parsing (original logic with selector validation)
        node_elements = _find_node_candidates(root)
        for idx, el in enumerate(node_elements):
            label = _node_label(el)
            step = _extract_step(label)
            center = _node_center(el)
            fallback = f"anim-node-{idx + 1}"
            selector, _ = _make_valid_selector(el, fallback)
            nodes.append(NodeInfo(
                element=el, label=label, center=center, step=step,
                anim_id=f"node-{idx + 1}", selector=selector
            ))

        for el in root.iter():
            tag = _strip_ns(el.tag)
            if tag not in {"path", "line", "polyline"}:
                continue
            if _is_descendant_of_any(el, node_elements):
                continue
            if tag == "line":
                x1 = _parse_float(el.get("x1"))
                y1 = _parse_float(el.get("y1"))
                x2 = _parse_float(el.get("x2"))
                y2 = _parse_float(el.get("y2"))
                center = ((x1 + x2) / 2, (y1 + y2) / 2)
            elif tag == "polyline":
                points = el.get("points") or ""
                coords = re.findall(r"([\-\d\.]+),([\-\d\.]+)", points)
                if coords:
                    xs = [float(x) for x, _ in coords]
                    ys = [float(y) for _, y in coords]
                    center = (sum(xs) / len(xs), sum(ys) / len(ys))
                else:
                    center = (0.0, 0.0)
            else:
                center = _center_from_path(el)
            
            fallback = f"anim-edge-{len(edges) + 1}"
            selector, _ = _make_valid_selector(el, fallback)
            edges.append(EdgeInfo(
                element=el, center=center,
                anim_id=f"edge-{len(edges) + 1}", selector=selector
            ))

    return ParsedSvg(root=root, nodes=nodes, edges=edges)
