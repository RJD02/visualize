"""Inject CSS animations into SVG content without changing geometry."""
from __future__ import annotations

import logging
import re
from typing import List, Set
from xml.etree import ElementTree as ET

from src.animation.animation_plan_generator import AnimationPlan

logger = logging.getLogger(__name__)

# Valid CSS ID selector pattern
VALID_CSS_SELECTOR_RE = re.compile(r"^[#.][a-zA-Z_][a-zA-Z0-9_-]*$")


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _ensure_style_element(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if _strip_ns(el.tag) == "style":
            return el
    style_el = ET.Element("style")
    root.insert(0, style_el)
    return style_el


def _register_svg_namespace() -> None:
    """Ensure the default SVG namespace is registered for serialization."""
    ET.register_namespace("", "http://www.w3.org/2000/svg")


def _is_valid_css_selector(selector: str) -> bool:
    """Check if a selector is valid CSS (no spaces, proper format)."""
    if not selector:
        return False
    # Simple selectors: #id or .class
    if VALID_CSS_SELECTOR_RE.match(selector):
        return True
    # Also allow compound selectors like "svg g" but not broken ones
    if " " in selector and not selector.startswith("#") and not selector.startswith("."):
        return True  # e.g., "svg g" is valid
    return False


def _validate_selectors(plan: AnimationPlan, root: ET.Element) -> List[str]:
    """
    Validate all selectors in the plan match elements in the SVG.
    Returns list of invalid/unmatched selectors.
    """
    invalid_selectors = []
    
    # Build set of all IDs and classes in the SVG
    all_ids: Set[str] = set()
    all_classes: Set[str] = set()
    for el in root.iter():
        el_id = el.get("id")
        if el_id:
            all_ids.add(el_id)
        el_class = el.get("class") or ""
        for cls in el_class.split():
            all_classes.add(cls)
    
    for step in plan.steps:
        selector = step.selector
        
        # Check for invalid CSS selector format
        if not _is_valid_css_selector(selector):
            invalid_selectors.append(f"INVALID FORMAT: '{selector}'")
            continue
        
        # Check if selector matches any element
        if selector.startswith("#"):
            target_id = selector[1:]
            if target_id not in all_ids:
                invalid_selectors.append(f"NO MATCH: '{selector}' (ID not found)")
        elif selector.startswith("."):
            target_class = selector[1:]
            if target_class not in all_classes:
                invalid_selectors.append(f"NO MATCH: '{selector}' (class not found)")
    
    return invalid_selectors


def build_animation_css(plan: AnimationPlan, debug: bool = False) -> str:
    """Generate CSS keyframes and per-step animation rules.
    
    Animation uses SVG-safe CSS properties:
    - opacity: fully supported
    - transform with transform-box: fill-box for proper origin
    - stroke properties for edge animations
    """
    lines: List[str] = [
        "/* SVG-safe animation defaults */",
        "svg * { transform-box: fill-box; transform-origin: center; }",
        ":root {",
        "  --anim-node-fill: #ffffff;",
        "  --anim-node-stroke: #334155;",
        "  --anim-edge-active: #0ea5e9;",
        "  --anim-text: #0f172a;",
        "  --anim-font: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;",
        "  --anim-font-weight: 500;",
        "}",
        "",
        "/* Node pulse animation - subtle scale and opacity */",
        "@keyframes animNodePulse {",
        "  0% { opacity: 0.4; }",
        "  50% { opacity: 1; }",
        "  100% { opacity: 0.4; }",
        "}",
        "/* Edge flow animation - stroke dash offset creates flow effect */",
        "@keyframes animEdgeFlow {",
        "  0% { stroke-dashoffset: 30; }",
        "  100% { stroke-dashoffset: 0; }",
        "}",
    ]

    if debug:
        lines.extend(
            [
                "/* Debug blink - proves animation is working */",
                "@keyframes debugBlink {",
                "  0% { opacity: 0.2; }",
                "  100% { opacity: 1; }",
                "}",
                "svg g { animation: debugBlink 0.5s infinite alternate; }",
            ]
        )

    for step in plan.steps:
        # Skip invalid selectors
        if not _is_valid_css_selector(step.selector):
            logger.warning(f"Skipping invalid selector: {step.selector}")
            continue
            
        if step.role == "node":
            # Use infinite animation so it keeps running
            # For nodes, animate the group (opacity works on groups)
            lines.append(
                f"{step.selector} rect, {step.selector} circle, {step.selector} ellipse, {step.selector} polygon, {step.selector} path {{ "
                f"fill: var(--anim-node-fill); stroke: var(--anim-node-stroke); }}"
            )
            lines.append(
                f"{step.selector} text {{ fill: var(--anim-text); font-family: var(--anim-font); font-weight: var(--anim-font-weight); }}"
            )
            lines.append(
                f"{step.selector} {{ animation: animNodePulse 1.5s ease-in-out {step.delay:.2f}s infinite; }}"
            )
        else:
            # Edge animation - MUST target actual path/line elements, not the group!
            # stroke-dasharray/dashoffset don't inherit to children in SVG
            selector = step.selector
            lines.append(
                f"{selector} path, {selector} line, {selector} polyline {{ stroke: var(--anim-edge-active); }}"
            )
            lines.append(
                f"{selector} path, {selector} line, {selector} polyline {{ "
                f"stroke-dasharray: 10 5; "
                f"animation: animEdgeFlow 1s linear {step.delay:.2f}s infinite; }}"
            )

    return "\n".join(lines)


def inject_css(svg_text: str, plan: AnimationPlan, debug: bool = False, strict: bool = False) -> str:
    """
    Inject CSS animations into SVG.
    
    Args:
        svg_text: The SVG content
        plan: Animation plan with selectors and timing
        debug: Add debug animations
        strict: If True, raise error when selectors don't match elements
    
    Returns:
        SVG with injected animation CSS
    """
    root = ET.fromstring(svg_text)
    
    # Validate selectors before injection
    invalid = _validate_selectors(plan, root)
    if invalid:
        for inv in invalid:
            logger.warning(f"Selector validation failed: {inv}")
        if strict:
            raise ValueError(f"Animation selectors failed validation: {invalid}")
    
    style_el = _ensure_style_element(root)
    css = build_animation_css(plan, debug=debug)
    existing = style_el.text or ""
    style_el.text = f"{existing}\n{css}\n"
    _register_svg_namespace()
    return ET.tostring(root, encoding="unicode")
