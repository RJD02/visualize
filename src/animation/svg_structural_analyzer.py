"""SVG Structural Analyzer - Extracts nodes, edges, groups, and builds a structural graph."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET


@dataclass
class SVGElement:
    """Base class for SVG structural elements."""
    id: str
    element_type: str
    selector: str
    label: str
    center: Tuple[float, float]
    bounds: Dict[str, float]  # x, y, width, height
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None


@dataclass
class SVGNode(SVGElement):
    """A node element (box, circle, etc.)"""
    role: str = "node"  # node, boundary, label
    zone: Optional[str] = None
    animatable_selector: Optional[str] = None  # Selector for the actual shape (rect/circle) to animate
    text_selector: Optional[str] = None  # Selector for the text element to animate


@dataclass
class SVGEdge(SVGElement):
    """An edge element (line, path connecting nodes)"""
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    edge_type: str = "directed"  # directed, undirected
    animatable_selector: Optional[str] = None  # Selector for the actual line/path to animate


@dataclass
class SVGGroup(SVGElement):
    """A group/cluster of elements"""
    member_ids: List[str] = field(default_factory=list)


@dataclass
class SVGStructuralGraph:
    """Complete structural representation of an SVG diagram."""
    svg_id: str
    diagram_type: str  # architecture, flow, sequence, etc.
    width: float
    height: float
    viewbox: str
    nodes: List[SVGNode] = field(default_factory=list)
    edges: List[SVGEdge] = field(default_factory=list)
    groups: List[SVGGroup] = field(default_factory=list)
    element_index: Dict[str, SVGElement] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "svg_id": self.svg_id,
            "diagram_type": self.diagram_type,
            "width": self.width,
            "height": self.height,
            "viewbox": self.viewbox,
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
            "groups": [asdict(g) for g in self.groups],
            "statistics": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "total_groups": len(self.groups),
            }
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


def _strip_ns(tag: str) -> str:
    """Remove XML namespace prefix from tag."""
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_float(value: Optional[str], default: float = 0.0) -> float:
    """Parse a float value safely."""
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _get_bounds_from_rect(el: ET.Element) -> Dict[str, float]:
    """Get bounding box from rect element."""
    return {
        "x": _parse_float(el.get("x")),
        "y": _parse_float(el.get("y")),
        "width": _parse_float(el.get("width")),
        "height": _parse_float(el.get("height")),
    }


def _get_center_from_bounds(bounds: Dict[str, float]) -> Tuple[float, float]:
    """Calculate center point from bounds."""
    return (
        bounds["x"] + bounds["width"] / 2,
        bounds["y"] + bounds["height"] / 2
    )


def _get_text_content(el: ET.Element) -> str:
    """Extract all text content from an element and its descendants."""
    texts = []
    for child in el.iter():
        if child.text:
            texts.append(child.text.strip())
        if child.tail:
            texts.append(child.tail.strip())
    return " ".join(t for t in texts if t)


def _get_element_attributes(el: ET.Element) -> Dict[str, str]:
    """Get relevant attributes from an element."""
    relevant = ["data-kind", "data-role", "class", "fill", "stroke"]
    return {k: v for k, v in el.attrib.items() if k in relevant or k.startswith("data-")}


def _infer_diagram_type(root: ET.Element) -> str:
    """Infer diagram type from SVG metadata or structure."""
    # Check data-diagram-type attribute
    dtype = root.get("data-diagram-type")
    if dtype:
        return dtype
    
    # Check metadata element
    for el in root.iter():
        if _strip_ns(el.tag) == "metadata":
            text = _get_text_content(el)
            if "sequence" in text.lower():
                return "sequence"
            if "component" in text.lower():
                return "component"
            if "container" in text.lower():
                return "container"
            if "context" in text.lower():
                return "system_context"
    
    return "architecture"


def _find_edge_endpoints(
    edge_el: ET.Element, 
    nodes: List[SVGNode]
) -> Tuple[Optional[str], Optional[str]]:
    """Find source and target nodes for an edge based on geometry."""
    tag = _strip_ns(edge_el.tag)
    
    # Get edge endpoints
    if tag == "line":
        x1 = _parse_float(edge_el.get("x1"))
        y1 = _parse_float(edge_el.get("y1"))
        x2 = _parse_float(edge_el.get("x2"))
        y2 = _parse_float(edge_el.get("y2"))
        start = (x1, y1)
        end = (x2, y2)
    elif tag == "path":
        d = edge_el.get("d") or ""
        # Extract first and last points from path
        points = re.findall(r"([\-\d\.]+)[,\s]+([\-\d\.]+)", d)
        if len(points) >= 2:
            start = (float(points[0][0]), float(points[0][1]))
            end = (float(points[-1][0]), float(points[-1][1]))
        else:
            return None, None
    else:
        return None, None
    
    # Find closest nodes to start and end points
    def closest_node(point: Tuple[float, float]) -> Optional[str]:
        min_dist = float("inf")
        closest = None
        for node in nodes:
            dist = ((node.center[0] - point[0]) ** 2 + (node.center[1] - point[1]) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                closest = node.id
        return closest
    
    return closest_node(start), closest_node(end)


def analyze_svg(svg_text: str, svg_id: str = "svg-1") -> SVGStructuralGraph:
    """
    Analyze SVG and extract structural graph.
    
    Returns a complete structural representation including:
    - All nodes (rectangles, circles, etc.)
    - All edges (lines, paths connecting nodes)
    - All groups (logical groupings)
    - Parent-child relationships
    - Connection topology
    """
    root = ET.fromstring(svg_text)
    
    # Get SVG dimensions
    width = _parse_float(root.get("width"), 960)
    height = _parse_float(root.get("height"), 720)
    viewbox = root.get("viewBox") or f"0 0 {width} {height}"
    diagram_type = _infer_diagram_type(root)
    
    graph = SVGStructuralGraph(
        svg_id=svg_id,
        diagram_type=diagram_type,
        width=width,
        height=height,
        viewbox=viewbox,
    )
    
    # Track element hierarchy
    element_parent: Dict[ET.Element, Optional[ET.Element]] = {root: None}
    
    def record_children(parent: ET.Element):
        for child in parent:
            element_parent[child] = parent
            record_children(child)
    record_children(root)
    
    # First pass: find all groups with IDs
    groups_by_el: Dict[ET.Element, SVGGroup] = {}
    for el in root.iter():
        if _strip_ns(el.tag) != "g":
            continue
        el_id = el.get("id")
        if not el_id:
            continue
        
        # PlantUML uses class="entity" or class="cluster" instead of data-kind
        el_class = el.get("class", "")
        data_kind = el.get("data-kind", "")
        data_role = el.get("data-role", "")
        
        # Map PlantUML classes to data-kind
        if "entity" in el_class:
            data_kind = data_kind or "node"
        elif "cluster" in el_class:
            data_kind = data_kind or "boundary"
        elif "link" in el_class:
            data_kind = data_kind or "edge"
        
        # Get label from text child
        label = ""
        for child in el:
            if _strip_ns(child.tag) == "text":
                label = _get_text_content(child)
                break
        
        # Get bounds from rect child if present, and find animatable element
        bounds = {"x": 0, "y": 0, "width": 0, "height": 0}
        animatable_child_id = None
        text_child_id = None
        animatable_child_elem = None
        text_child_elem = None
        for child in el:
            child_tag = _strip_ns(child.tag)
            if child_tag == "rect":
                bounds = _get_bounds_from_rect(child)
                child_id = child.get("id")
                if child_id:
                    animatable_child_id = child_id
                else:
                    animatable_child_elem = child
            elif child_tag in ("circle", "ellipse", "polygon", "path"):
                child_id = child.get("id")
                if child_id and not animatable_child_id:
                    animatable_child_id = child_id
                elif not animatable_child_elem:
                    animatable_child_elem = child
            elif child_tag == "text":
                child_id = child.get("id")
                if child_id:
                    text_child_id = child_id
                else:
                    text_child_elem = child
        
        center = _get_center_from_bounds(bounds)
        
        if data_kind == "node":
            # This is a node, not a group
            # Use the child rect/shape for animation if available
            # If no ID, use CSS selector targeting child element within parent
            if animatable_child_id:
                anim_selector = f"#{animatable_child_id}"
            elif animatable_child_elem is not None:
                # Use descendant selector: #parent-id rect
                anim_selector = f"#{el_id} rect"
            else:
                anim_selector = f"#{el_id}"
            
            if text_child_id:
                text_selector = f"#{text_child_id}"
            elif text_child_elem is not None:
                # Use descendant selector: #parent-id text
                text_selector = f"#{el_id} text"
            else:
                text_selector = None
            node = SVGNode(
                id=el_id,
                element_type="node",
                selector=f"#{el_id}",
                label=label or el_id,
                center=center,
                bounds=bounds,
                attributes=_get_element_attributes(el),
                role=data_role or "node",
                zone=el.get("data-zone"),
                animatable_selector=anim_selector,
                text_selector=text_selector,
            )
            graph.nodes.append(node)
            graph.element_index[el_id] = node
            
        elif data_kind == "boundary":
            # Boundary is a special group
            group = SVGGroup(
                id=el_id,
                element_type="boundary",
                selector=f"#{el_id}",
                label=label or data_role or el_id,
                center=center,
                bounds=bounds,
                attributes=_get_element_attributes(el),
            )
            graph.groups.append(group)
            graph.element_index[el_id] = group
            groups_by_el[el] = group
            
        elif data_kind == "edge":
            # Edge wrapped in a group
            # Find the actual line/path inside
            for child in el:
                tag = _strip_ns(child.tag)
                if tag in ("line", "path", "polyline"):
                    edge_id = child.get("id") or el_id
                    
                    # Get edge geometry
                    if tag == "line":
                        x1 = _parse_float(child.get("x1"))
                        y1 = _parse_float(child.get("y1"))
                        x2 = _parse_float(child.get("x2"))
                        y2 = _parse_float(child.get("y2"))
                        center = ((x1 + x2) / 2, (y1 + y2) / 2)
                        bounds = {"x": min(x1, x2), "y": min(y1, y2), 
                                  "width": abs(x2 - x1), "height": abs(y2 - y1)}
                    else:
                        center = (0, 0)
                        bounds = {"x": 0, "y": 0, "width": 0, "height": 0}
                    
                    # Use the actual line/path element for animation
                    edge = SVGEdge(
                        id=edge_id,
                        element_type="edge",
                        selector=f"#{edge_id}",
                        label=label,
                        center=center,
                        bounds=bounds,
                        attributes=_get_element_attributes(el),
                        edge_type=data_role or "directed",
                        animatable_selector=f"#{edge_id}",  # The line element itself is animatable
                    )
                    graph.edges.append(edge)
                    graph.element_index[edge_id] = edge
                    break
        
        elif data_kind == "label":
            # Label element - treat as a special node
            # Find text child for animation
            text_child_id = None
            for child in el:
                if _strip_ns(child.tag) == "text":
                    text_id = child.get("id")
                    if text_id:
                        text_child_id = text_id
                    break
            
            anim_selector = f"#{text_child_id}" if text_child_id else f"#{el_id}"
            node = SVGNode(
                id=el_id,
                element_type="label",
                selector=f"#{el_id}",
                label=label or el_id,
                center=center,
                bounds=bounds,
                attributes=_get_element_attributes(el),
                role="label",
                animatable_selector=anim_selector,
            )
            graph.nodes.append(node)
            graph.element_index[el_id] = node
    
    # Second pass: find standalone edges (not in groups)
    for el in root.iter():
        tag = _strip_ns(el.tag)
        if tag not in ("line", "path", "polyline"):
            continue
        
        el_id = el.get("id")
        if not el_id or el_id in graph.element_index:
            continue
        
        # Check if parent is an edge group
        parent = element_parent.get(el)
        if parent is not None and parent.get("data-kind") == "edge":
            continue
        
        # Get edge geometry
        if tag == "line":
            x1 = _parse_float(el.get("x1"))
            y1 = _parse_float(el.get("y1"))
            x2 = _parse_float(el.get("x2"))
            y2 = _parse_float(el.get("y2"))
            center = ((x1 + x2) / 2, (y1 + y2) / 2)
            bounds = {"x": min(x1, x2), "y": min(y1, y2),
                      "width": abs(x2 - x1), "height": abs(y2 - y1)}
        else:
            d = el.get("d") or ""
            points = re.findall(r"([\-\d\.]+)[,\s]+([\-\d\.]+)", d)
            if points:
                xs = [float(p[0]) for p in points]
                ys = [float(p[1]) for p in points]
                center = (sum(xs) / len(xs), sum(ys) / len(ys))
                bounds = {"x": min(xs), "y": min(ys),
                          "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
            else:
                center = (0, 0)
                bounds = {"x": 0, "y": 0, "width": 0, "height": 0}
        
        edge = SVGEdge(
            id=el_id,
            element_type="edge",
            selector=f"#{el_id}",
            label="",
            center=center,
            bounds=bounds,
            attributes=_get_element_attributes(el),
        )
        graph.edges.append(edge)
        graph.element_index[el_id] = edge
    
    # Third pass: resolve edge connections
    for edge in graph.edges:
        # Try to find source/target from ID pattern
        # e.g., edge_node1_node2_sync
        parts = edge.id.split("_")
        if len(parts) >= 3 and parts[0] == "edge":
            # Try to match node IDs in the edge ID
            for node in graph.nodes:
                if node.id in edge.id:
                    if edge.source_id is None:
                        edge.source_id = node.id
                    elif edge.target_id is None and node.id != edge.source_id:
                        edge.target_id = node.id
    
    # Assign nodes to groups based on position
    for group in graph.groups:
        if group.bounds["width"] > 0 and group.bounds["height"] > 0:
            gx, gy = group.bounds["x"], group.bounds["y"]
            gw, gh = group.bounds["width"], group.bounds["height"]
            for node in graph.nodes:
                nx, ny = node.center
                if gx <= nx <= gx + gw and gy <= ny <= gy + gh:
                    group.member_ids.append(node.id)
                    node.parent_id = group.id
    
    # Fourth pass: find standalone shape elements as nodes
    # (rects, circles, ellipses, polygons that are not already processed)
    for el in root.iter():
        tag = _strip_ns(el.tag)
        if tag not in ("rect", "circle", "ellipse", "polygon"):
            continue
        
        el_id = el.get("id")
        if not el_id or el_id in graph.element_index:
            continue
        
        # Check if parent is a node group (already processed)
        parent = element_parent.get(el)
        if parent is not None and parent.get("data-kind") == "node":
            continue
        
        # Get geometry based on element type
        if tag == "rect":
            bounds = _get_bounds_from_rect(el)
            center = _get_center_from_bounds(bounds)
        elif tag == "circle":
            cx = _parse_float(el.get("cx"))
            cy = _parse_float(el.get("cy"))
            r = _parse_float(el.get("r"))
            center = (cx, cy)
            bounds = {"x": cx - r, "y": cy - r, "width": r * 2, "height": r * 2}
        elif tag == "ellipse":
            cx = _parse_float(el.get("cx"))
            cy = _parse_float(el.get("cy"))
            rx = _parse_float(el.get("rx"))
            ry = _parse_float(el.get("ry"))
            center = (cx, cy)
            bounds = {"x": cx - rx, "y": cy - ry, "width": rx * 2, "height": ry * 2}
        elif tag == "polygon":
            points_str = el.get("points") or ""
            points = re.findall(r"([\-\d\.]+)[,\s]+([\-\d\.]+)", points_str)
            if points:
                xs = [float(p[0]) for p in points]
                ys = [float(p[1]) for p in points]
                center = (sum(xs) / len(xs), sum(ys) / len(ys))
                bounds = {"x": min(xs), "y": min(ys),
                          "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
            else:
                center = (0, 0)
                bounds = {"x": 0, "y": 0, "width": 0, "height": 0}
        else:
            continue
        
        # Get label from nearby text element
        label = ""
        # Check for text sibling or child
        search_root = parent if parent is not None else root
        for sibling in search_root:
            if _strip_ns(sibling.tag) == "text":
                sibling_text = _get_text_content(sibling)
                if sibling_text:
                    label = sibling_text
                    break
        
        node = SVGNode(
            id=el_id,
            element_type="node",
            selector=f"#{el_id}",
            label=label or el_id,
            center=center,
            bounds=bounds,
            attributes=_get_element_attributes(el),
            role="node",
        )
        graph.nodes.append(node)
        graph.element_index[el_id] = node
    
    return graph


def compare_structures(
    original: SVGStructuralGraph, 
    modified: SVGStructuralGraph
) -> Dict[str, Any]:
    """
    Compare two SVG structures to detect semantic drift.
    
    Returns a comparison report with:
    - is_equivalent: True if structures are semantically equivalent
    - differences: List of detected differences
    """
    differences = []
    
    # Compare node counts
    orig_node_ids = {n.id for n in original.nodes}
    mod_node_ids = {n.id for n in modified.nodes}
    
    added_nodes = mod_node_ids - orig_node_ids
    removed_nodes = orig_node_ids - mod_node_ids
    
    if added_nodes:
        differences.append({
            "type": "nodes_added",
            "severity": "error",
            "ids": list(added_nodes),
            "message": f"New nodes were added: {added_nodes}"
        })
    
    if removed_nodes:
        differences.append({
            "type": "nodes_removed",
            "severity": "error",
            "ids": list(removed_nodes),
            "message": f"Nodes were removed: {removed_nodes}"
        })
    
    # Compare edge counts
    orig_edge_ids = {e.id for e in original.edges}
    mod_edge_ids = {e.id for e in modified.edges}
    
    added_edges = mod_edge_ids - orig_edge_ids
    removed_edges = orig_edge_ids - mod_edge_ids
    
    if added_edges:
        differences.append({
            "type": "edges_added",
            "severity": "error",
            "ids": list(added_edges),
            "message": f"New edges were added: {added_edges}"
        })
    
    if removed_edges:
        differences.append({
            "type": "edges_removed",
            "severity": "error",
            "ids": list(removed_edges),
            "message": f"Edges were removed: {removed_edges}"
        })
    
    # Compare edge connections (topology)
    for orig_edge in original.edges:
        mod_edge = next((e for e in modified.edges if e.id == orig_edge.id), None)
        if mod_edge:
            if orig_edge.source_id != mod_edge.source_id or orig_edge.target_id != mod_edge.target_id:
                differences.append({
                    "type": "edge_reconnected",
                    "severity": "error",
                    "edge_id": orig_edge.id,
                    "message": f"Edge {orig_edge.id} was reconnected"
                })
    
    # Compare group membership
    for orig_group in original.groups:
        mod_group = next((g for g in modified.groups if g.id == orig_group.id), None)
        if mod_group:
            orig_members = set(orig_group.member_ids)
            mod_members = set(mod_group.member_ids)
            if orig_members != mod_members:
                differences.append({
                    "type": "group_membership_changed",
                    "severity": "warning",
                    "group_id": orig_group.id,
                    "message": f"Group {orig_group.id} membership changed"
                })
    
    is_equivalent = len([d for d in differences if d["severity"] == "error"]) == 0
    
    return {
        "is_equivalent": is_equivalent,
        "differences": differences,
        "original_stats": {
            "nodes": len(original.nodes),
            "edges": len(original.edges),
            "groups": len(original.groups),
        },
        "modified_stats": {
            "nodes": len(modified.nodes),
            "edges": len(modified.edges),
            "groups": len(modified.groups),
        }
    }
