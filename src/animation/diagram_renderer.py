"""Render static or animated SVG diagrams using inferred animation plans."""
from __future__ import annotations

import uuid
from xml.etree import ElementTree as ET
import base64
import re
from typing import Union

from src.animation.svg_parser import ParsedSvg, parse_svg
from src.animation.animation_plan_generator import generate_animation_plan
from src.animation.css_injector import inject_css

# New animation system imports
from src.animation.svg_structural_analyzer import analyze_svg
from src.animation.animation_plan_schema import (
    AnimationPlanV2,
    AnimationSequence,
    ElementAnimation,
    AnimationType,
    ANIMATION_PRESETS,
)
from src.animation.animation_executor import inject_animation
from src.animation.semantic_invariance_checker import validate_animation_safety
from src.aesthetics.style_transformer import apply_aesthetic_plan
from src.aesthetics.visual_grammar import build_aesthetic_plan
from src.intent.semantic_aesthetic_ir import SemanticAestheticIR


def _has_svg_root(svg_text: str) -> bool:
    """Return True if the payload parses into an <svg> root element."""
    if svg_text is None:
        return False
    try:
        root = ET.fromstring(svg_text.strip())
    except Exception:
        return False
    tag = root.tag
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    elif ":" in tag:
        tag = tag.split(":", 1)[1]
    return tag.lower() == "svg"


def _append_class(el: ET.Element, class_name: str) -> None:
    existing = el.get("class") or ""
    classes = [c for c in existing.split() if c]
    if class_name not in classes:
        classes.append(class_name)
    el.set("class", " ".join(classes))

def _annotate_elements(parsed: ParsedSvg) -> None:
    for node in parsed.nodes:
        if node.selector.startswith("."):
            _append_class(node.element, node.selector[1:])
    for edge in parsed.edges:
        if edge.selector.startswith("."):
            _append_class(edge.element, edge.selector[1:])


def render_svg(
    svg_text: str,
    animated: bool,
    debug: bool = False,
    use_v2: bool = False,
    enhanced: bool = False,
    semantic_intent: SemanticAestheticIR | None = None,
) -> str:
    """Return SVG with optional CSS animation injected.

    This does not change layout/geometry; it only adds class attributes and style rules.
    
    Args:
        svg_text: Raw SVG content
        animated: Whether to inject animations
        debug: Add debug styling
        use_v2: Use new animation system (default True)
    """
    if svg_text is None or not str(svg_text).strip():
        return svg_text or ""
    # If the incoming payload is not SVG (e.g., PNG bytes or a base64 image),
    # and the caller requested animation, wrap it inside an SVG <image/>
    def _is_svg(s: str) -> bool:
        return _has_svg_root(s)

    def _wrap_non_svg(s: Union[str, bytes]) -> str:
        # Accept raw bytes or a string that may be base64 or raw binary mapped into a str.
        if isinstance(s, bytes):
            b = s
            mime = "image/png"
            data = base64.b64encode(b).decode("ascii")
            data_url = f"data:{mime};base64,{data}"
        else:
            s_strip = s.strip()
            if s_strip.startswith("data:"):
                data_url = s_strip
            elif re.fullmatch(r"[A-Za-z0-9+/=\n\r]+", s_strip):
                # Looks like base64 without data: prefix — assume PNG
                data_url = f"data:image/png;base64,{s_strip.replace('\n','').replace('\r','')}"
            else:
                # Fallback: base64-encode the UTF-8 bytes of the string
                b = s.encode("utf-8", errors="ignore")
                data = base64.b64encode(b).decode("ascii")
                data_url = f"data:image/png;base64,{data}"

        return f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"><image href="{data_url}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet"/></svg>'
    if not animated:
        if enhanced:
            intent = semantic_intent or SemanticAestheticIR()
            graph = analyze_svg(svg_text, "svg-aesthetic")
            plan, highlights = build_aesthetic_plan(intent, graph)
            return apply_aesthetic_plan(svg_text, plan, graph=graph, highlight_override=highlights)
        return svg_text

    # If requested animation but input isn't SVG, wrap it so we can still apply
    # container-level animations. Prefer this wrapping only for animated flows.
    if animated and not _is_svg(svg_text):
        svg_text = _wrap_non_svg(svg_text)

    if use_v2:
        return render_svg_v2(svg_text, debug=debug, enhanced=enhanced, semantic_intent=semantic_intent)
    
    # Legacy path
    parsed = parse_svg(svg_text)
    _annotate_elements(parsed)
    annotated_svg = ET.tostring(parsed.root, encoding="unicode")
    plan = generate_animation_plan(parsed)
    animated_svg = inject_css(annotated_svg, plan, debug=debug)
    return animated_svg


def render_svg_v2(
    svg_text: str,
    debug: bool = False,
    enhanced: bool = False,
    semantic_intent: SemanticAestheticIR | None = None,
) -> str:
    """Render SVG with new animation system (v2).
    
    Uses SVG structural analysis, generates animation plan,
    and executes with CSS injection.
    """
    # Optionally apply aesthetic intelligence before animation
    if enhanced:
        intent = semantic_intent or SemanticAestheticIR()
        graph = analyze_svg(svg_text, "svg-aesthetic")
        plan, highlights = build_aesthetic_plan(intent, graph)
        svg_text = apply_aesthetic_plan(svg_text, plan, graph=graph, highlight_override=highlights)

    # If incoming content is not SVG (e.g., PNG bytes), wrap it so v2 can still
    # generate a container-level animation. This preserves the image visually
    # while enabling simple CSS effects on the outer SVG/image element.
    if not _has_svg_root(svg_text):
        # Reuse the same wrapping logic as render_svg
        b = svg_text.encode("utf-8", errors="ignore")
        data = base64.b64encode(b).decode("ascii")
        data_url = f"data:image/png;base64,{data}"
        svg_text = f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%"><image href="{data_url}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" id="embedded_img"/></svg>'

    # Analyze SVG structure
    svg_id = f"svg-{uuid.uuid4().hex[:8]}"
    graph = analyze_svg(svg_text, svg_id)

    intent = semantic_intent or SemanticAestheticIR()
    node_focus = set(k.lower() for k, v in intent.nodeIntent.items() if v.importance == "primary" or v.attention == "focus")
    edge_focus = set(k.lower() for k, v in intent.edgeIntent.items() if v.activity == "active" or v.criticality == "high")
    
    # Generate animation plan from structure
    elements = []
    delay = 0.0
    gap = 0.05  # Reduced gap for faster start

    # Animate nodes with pulse effect
    for i, node in enumerate(graph.nodes):
        preset = ANIMATION_PRESETS["node_pulse"]
        # Use animatable_selector for the actual shape element (rect, circle, etc.)
        anim_selector = node.animatable_selector or f"#{node.id}"
        label_key = (node.label or node.id or "").lower()
        anim_type = preset["animation_type"]
        if label_key in node_focus:
            anim_type = AnimationType.GLOW
        elements.append(ElementAnimation(
            element_id=node.id,
            selector=anim_selector,
            element_type=node.element_type,
            animation_type=anim_type,
            delay=delay,
            duration=preset["duration"],
            iterations=preset["iterations"],
            direction=preset["direction"],
        ))
        
        # Also animate text element if present
        if node.text_selector:
            elements.append(ElementAnimation(
                element_id=f"{node.id}_text",
                selector=node.text_selector,
                element_type="text",
                animation_type=AnimationType.PULSE,
                delay=delay,  # Same delay as the shape
                duration=preset["duration"],
                iterations=preset["iterations"],
                direction=preset["direction"],
            ))
        
        delay += gap
    
    # Animate edges with flow effect  
    for i, edge in enumerate(graph.edges):
        preset = ANIMATION_PRESETS["edge_flow"]
        # Use animatable_selector for the actual line/path element
        anim_selector = edge.animatable_selector or f"#{edge.id}"
        edge_key = f"{(edge.source_id or '').lower()}->{(edge.target_id or '').lower()}"
        anim_type = preset["animation_type"]
        if edge_key in edge_focus:
            anim_type = AnimationType.FLOW
        elements.append(ElementAnimation(
            element_id=edge.id,
            selector=anim_selector,
            element_type=edge.element_type,
            animation_type=anim_type,
            delay=delay,
            duration=preset["duration"],
            iterations=preset["iterations"],
            direction=preset["direction"],
        ))
        delay += gap * 0.5  # Even shorter delay between edges
    
    plan = AnimationPlanV2(
        plan_id=f"plan-{uuid.uuid4().hex[:8]}",
        svg_id=svg_id,
        diagram_type=graph.diagram_type,
        description=f"Auto-generated animation for {graph.diagram_type} diagram",
        style="professional",
        sequences=[
            AnimationSequence(
                name="main",
                description="Main animation sequence",
                elements=elements,
                parallel=True,
                loop=True,
            )
        ],
        global_settings={
            "respect_reduced_motion": True,
            "debug": debug,
        },
    )
    
    # Inject animations
    animated_svg = inject_animation(svg_text, plan, use_js=False)
    
    # Validate semantic invariance
    is_safe, message = validate_animation_safety(svg_text, animated_svg)
    if not is_safe:
        # Log warning but still return animated SVG
        import logging
        logging.warning(f"Animation safety check failed: {message}")
    
    return animated_svg
