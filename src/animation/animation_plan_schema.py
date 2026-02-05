"""Animation Plan Schema - Defines the structure of animation plans."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class AnimationType(str, Enum):
    """Types of animations that can be applied."""
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"
    PULSE = "pulse"
    GLOW = "glow"
    SCALE = "scale"
    SLIDE = "slide"
    FLOW = "flow"
    DRAW = "draw"
    HIGHLIGHT = "highlight"
    WAVE = "wave"
    BOUNCE = "bounce"
    NONE = "none"


class EasingFunction(str, Enum):
    """Easing functions for animations."""
    LINEAR = "linear"
    EASE = "ease"
    EASE_IN = "ease-in"
    EASE_OUT = "ease-out"
    EASE_IN_OUT = "ease-in-out"
    CUBIC_BEZIER = "cubic-bezier"


@dataclass
class AnimationKeyframe:
    """A single keyframe in an animation."""
    offset: float  # 0.0 to 1.0
    properties: Dict[str, Any]  # CSS properties at this keyframe


@dataclass
class ElementAnimation:
    """Animation configuration for a single SVG element."""
    selector: str
    element_id: str
    element_type: str  # node, edge, group, label
    animation_type: AnimationType
    delay: float = 0.0
    duration: float = 1.0
    iterations: int = -1  # -1 for infinite
    direction: str = "normal"  # normal, reverse, alternate
    easing: EasingFunction = EasingFunction.EASE_IN_OUT
    keyframes: List[AnimationKeyframe] = field(default_factory=list)
    fill_mode: str = "both"  # none, forwards, backwards, both
    custom_css: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnimationSequence:
    """A sequence of animations that play together or in order."""
    name: str
    description: str
    elements: List[ElementAnimation]
    parallel: bool = True  # True = play together, False = sequential
    loop: bool = True
    total_duration: float = 0.0


@dataclass
class AnimationPlanV2:
    """
    Complete animation plan for an SVG diagram.
    
    This plan is produced by the Animation Intelligence LLM and
    consumed by the Animation Executor to render animations.
    """
    plan_id: str
    svg_id: str
    diagram_type: str
    description: str
    style: str  # e.g., "architectural-flow", "storytelling", "technical"
    sequences: List[AnimationSequence] = field(default_factory=list)
    global_settings: Dict[str, Any] = field(default_factory=dict)
    css_keyframes: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        def convert(obj):
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, '__dataclass_fields__'):
                return {k: convert(v) for k, v in asdict(obj).items()}
            if isinstance(obj, list):
                return [convert(i) for i in obj]
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            return obj
        return convert(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AnimationPlanV2":
        """Create from dictionary."""
        sequences = []
        for seq_data in data.get("sequences", []):
            elements = []
            for elem_data in seq_data.get("elements", []):
                keyframes = [
                    AnimationKeyframe(**kf) for kf in elem_data.get("keyframes", [])
                ]
                elem = ElementAnimation(
                    selector=elem_data["selector"],
                    element_id=elem_data["element_id"],
                    element_type=elem_data["element_type"],
                    animation_type=AnimationType(elem_data.get("animation_type", "pulse")),
                    delay=elem_data.get("delay", 0.0),
                    duration=elem_data.get("duration", 1.0),
                    iterations=elem_data.get("iterations", -1),
                    direction=elem_data.get("direction", "normal"),
                    easing=EasingFunction(elem_data.get("easing", "ease-in-out")),
                    keyframes=keyframes,
                    fill_mode=elem_data.get("fill_mode", "both"),
                    custom_css=elem_data.get("custom_css"),
                    metadata=elem_data.get("metadata", {}),
                )
                elements.append(elem)
            
            seq = AnimationSequence(
                name=seq_data["name"],
                description=seq_data.get("description", ""),
                elements=elements,
                parallel=seq_data.get("parallel", True),
                loop=seq_data.get("loop", True),
                total_duration=seq_data.get("total_duration", 0.0),
            )
            sequences.append(seq)
        
        return cls(
            plan_id=data["plan_id"],
            svg_id=data["svg_id"],
            diagram_type=data.get("diagram_type", "architecture"),
            description=data.get("description", ""),
            style=data.get("style", "default"),
            sequences=sequences,
            global_settings=data.get("global_settings", {}),
            css_keyframes=data.get("css_keyframes", {}),
            metadata=data.get("metadata", {}),
        )


# Default animation presets for different element types
ANIMATION_PRESETS = {
    "node_pulse": {
        "animation_type": AnimationType.PULSE,
        "duration": 1.5,  # Faster for more visible effect
        "iterations": -1,
        "direction": "alternate",
        "keyframes": [
            {"offset": 0.0, "properties": {"opacity": 0.3}},  # Much more dramatic
            {"offset": 0.5, "properties": {"opacity": 1.0}},
            {"offset": 1.0, "properties": {"opacity": 0.3}},
        ]
    },
    "node_glow": {
        "animation_type": AnimationType.GLOW,
        "duration": 1.5,
        "iterations": -1,
        "direction": "alternate",
        "keyframes": [
            {"offset": 0.0, "properties": {"filter": "drop-shadow(0 0 0px #60a5fa)"}},
            {"offset": 0.5, "properties": {"filter": "drop-shadow(0 0 8px #60a5fa)"}},
            {"offset": 1.0, "properties": {"filter": "drop-shadow(0 0 0px #60a5fa)"}},
        ]
    },
    "edge_flow": {
        "animation_type": AnimationType.FLOW,
        "duration": 1.0,  # Faster for visible movement
        "iterations": -1,
        "direction": "normal",  # Always forward for continuous flow
        "keyframes": [
            # Animate dashoffset by the dasharray pattern length (10+5=15) * 2 = 30
            # This creates smooth continuous "marching ants" effect
            {"offset": 0.0, "properties": {"stroke-dashoffset": 30}},
            {"offset": 1.0, "properties": {"stroke-dashoffset": 0}},
        ]
    },
    "edge_draw": {
        "animation_type": AnimationType.DRAW,
        "duration": 1.5,
        "iterations": 1,
        "direction": "normal",
        "keyframes": [
            {"offset": 0.0, "properties": {"stroke-dashoffset": 1000}},
            {"offset": 1.0, "properties": {"stroke-dashoffset": 0}},
        ]
    },
    "group_highlight": {
        "animation_type": AnimationType.HIGHLIGHT,
        "duration": 2.5,
        "iterations": -1,
        "direction": "alternate",
        "keyframes": [
            {"offset": 0.0, "properties": {"opacity": 0.3}},
            {"offset": 0.5, "properties": {"opacity": 0.6}},
            {"offset": 1.0, "properties": {"opacity": 0.3}},
        ]
    },
    "label_fade": {
        "animation_type": AnimationType.FADE_IN,
        "duration": 1.0,
        "iterations": 1,
        "direction": "normal",
        "keyframes": [
            {"offset": 0.0, "properties": {"opacity": 0}},
            {"offset": 1.0, "properties": {"opacity": 1}},
        ]
    },
}


def create_default_plan(
    svg_id: str,
    diagram_type: str,
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    groups: List[Dict[str, Any]],
) -> AnimationPlanV2:
    """
    Create a default animation plan based on diagram structure.
    
    This is a fallback when the LLM is not available.
    """
    elements = []
    delay = 0.0
    gap = 0.1
    
    # Animate nodes with pulse
    for node in nodes:
        preset = ANIMATION_PRESETS["node_pulse"]
        elements.append(ElementAnimation(
            selector=f"#{node['id']}",
            element_id=node['id'],
            element_type="node",
            animation_type=preset["animation_type"],
            delay=delay,
            duration=preset["duration"],
            iterations=preset["iterations"],
            direction=preset["direction"],
            keyframes=[AnimationKeyframe(**kf) for kf in preset["keyframes"]],
        ))
        delay += gap
    
    # Animate edges with flow
    for edge in edges:
        preset = ANIMATION_PRESETS["edge_flow"]
        elements.append(ElementAnimation(
            selector=f"#{edge['id']}",
            element_id=edge['id'],
            element_type="edge",
            animation_type=preset["animation_type"],
            delay=delay,
            duration=preset["duration"],
            iterations=preset["iterations"],
            direction=preset["direction"],
            keyframes=[AnimationKeyframe(**kf) for kf in preset["keyframes"]],
        ))
        delay += gap
    
    sequence = AnimationSequence(
        name="main",
        description="Default animation sequence",
        elements=elements,
        parallel=True,
        loop=True,
        total_duration=delay + 2.0,
    )
    
    return AnimationPlanV2(
        plan_id=f"plan-{svg_id}",
        svg_id=svg_id,
        diagram_type=diagram_type,
        description="Default animation plan",
        style="default",
        sequences=[sequence],
        global_settings={
            "respect_reduced_motion": True,
            "fallback_to_static": True,
        },
    )
