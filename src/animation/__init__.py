"""Animation System Module.

This module provides intelligent, LLM-powered animations for SVG diagrams.

Components:
- svg_structural_analyzer: Extracts structural graph from SVG
- animation_plan_schema: Defines animation plan data structures
- animation_intelligence: MCP tool for LLM-based animation planning
- animation_executor: Generates CSS/JS animations from plans
- semantic_invariance_checker: Validates animations don't corrupt SVG
"""

from src.animation.svg_structural_analyzer import (
    SVGNode,
    SVGEdge,
    SVGGroup,
    SVGStructuralGraph,
    analyze_svg,
    compare_structures,
)

from src.animation.animation_plan_schema import (
    AnimationPlanV2,
    AnimationSequence,
    ElementAnimation,
    AnimationKeyframe,
    AnimationType,
    EasingFunction,
    ANIMATION_PRESETS,
)

from src.animation.animation_executor import (
    generate_animation_css,
    generate_animation_js,
    inject_animation,
    create_animated_html,
)

from src.animation.semantic_invariance_checker import (
    check_semantic_invariance,
    validate_animation_safety,
    InvarianceCheckResult,
    InvarianceViolation,
    InvarianceViolationType,
    report_violations,
)

__all__ = [
    # Structural Analysis
    "SVGNode",
    "SVGEdge", 
    "SVGGroup",
    "SVGStructuralGraph",
    "analyze_svg",
    "compare_structures",
    # Plan Schema
    "AnimationPlanV2",
    "AnimationSequence",
    "ElementAnimation",
    "AnimationKeyframe",
    "AnimationType",
    "EasingFunction",
    "ANIMATION_PRESETS",
    # Executor
    "generate_animation_css",
    "generate_animation_js",
    "inject_animation",
    "create_animated_html",
    # Invariance Checker
    "check_semantic_invariance",
    "validate_animation_safety",
    "InvarianceCheckResult",
    "InvarianceViolation",
    "InvarianceViolationType",
    "report_violations",
]
