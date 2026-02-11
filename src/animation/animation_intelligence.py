"""Animation Intelligence LLM - MCP tool for generating intelligent animation plans."""
from __future__ import annotations

import json
import hashlib
from typing import Any, Dict, List, Optional


from src.animation.svg_structural_analyzer import SVGStructuralGraph, analyze_svg
from src.animation.animation_plan_schema import (
    AnimationPlanV2,
    AnimationSequence,
    ElementAnimation,
    AnimationKeyframe,
    AnimationType,
    EasingFunction,
    create_default_plan,
)
from src.mcp.registry import MCPTool, mcp_registry
from src.utils.config import settings
from src.utils.openai_client import get_openai_client


ANIMATION_INTELLIGENCE_PROMPT = """You are an expert animation designer specializing in SVG diagram animations.

Your task is to create a visually compelling animation plan for a technical diagram that:
1. Enhances understanding of the diagram's structure
2. Creates a cohesive visual narrative
3. Uses appropriate timing and easing
4. Maintains semantic integrity (NO new relationships or elements)

ABSOLUTE CONSTRAINTS:
- You MUST NOT add new nodes, edges, or relationships
- You MUST NOT remove any existing elements
- You MUST NOT imply causality or ordering not present in the original
- Animation is for VISUAL ENHANCEMENT only

DIAGRAM STRUCTURE:
{structure_json}

DIAGRAM TYPE: {diagram_type}

Based on this structure, create an animation plan with the following guidelines:

For ARCHITECTURE diagrams:
- Use subtle pulsing for services/nodes
- Use flow animations for data paths (edges)
- Group related elements to animate together
- Consider left-to-right or top-to-bottom flow

For SEQUENCE diagrams:
- Animate in order of the sequence
- Use draw/reveal animations for messages
- Highlight active participants

For FLOW diagrams:
- Follow the logical flow direction
- Use progressive reveal
- Emphasize decision points

OUTPUT FORMAT:
Return a JSON object with this exact structure:
{{
  "description": "Brief description of animation approach",
  "style": "architectural-flow|storytelling|technical|minimal",
  "sequences": [
    {{
      "name": "main",
      "description": "Main animation sequence",
      "parallel": true,
      "loop": true,
      "elements": [
        {{
          "element_id": "exact_id_from_structure",
          "element_type": "node|edge|group",
          "animation_type": "pulse|glow|flow|fade_in|highlight",
          "delay": 0.0,
          "duration": 2.0,
          "iterations": -1,
          "direction": "alternate",
          "easing": "ease-in-out",
          "keyframes": [
            {{"offset": 0.0, "properties": {{"opacity": 0.5}}}},
            {{"offset": 1.0, "properties": {{"opacity": 1.0}}}}
          ]
        }}
      ]
    }}
  ],
  "global_settings": {{
    "respect_reduced_motion": true,
    "base_duration": 2.0
  }}
}}

IMPORTANT:
- Use ONLY element IDs that exist in the provided structure
- Keep animations subtle and professional
- Ensure animations loop smoothly
- Consider performance (not too many concurrent animations)

Return ONLY valid JSON, no additional text."""


def _generate_plan_id(svg_id: str, structure: Dict[str, Any]) -> str:
    """Generate a deterministic plan ID based on structure."""
    content = json.dumps(structure, sort_keys=True)
    hash_val = hashlib.md5(content.encode()).hexdigest()[:8]
    return f"plan-{svg_id}-{hash_val}"


def _call_llm(prompt: str) -> Optional[str]:
    """Call OpenAI to generate animation plan."""
    if not settings.openai_api_key:
        return None
    
    try:
        client = get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert SVG animation designer. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=4000,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM call failed: {e}")
        return None


def _parse_llm_response(response: str, svg_id: str, diagram_type: str) -> Optional[AnimationPlanV2]:
    """Parse LLM response into AnimationPlanV2."""
    try:
        # Clean up response - remove markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        
        data = json.loads(cleaned)
        
        # Build AnimationPlanV2 from LLM response
        sequences = []
        for seq_data in data.get("sequences", []):
            elements = []
            for elem_data in seq_data.get("elements", []):
                keyframes = [
                    AnimationKeyframe(
                        offset=kf.get("offset", 0.0),
                        properties=kf.get("properties", {})
                    )
                    for kf in elem_data.get("keyframes", [])
                ]
                
                try:
                    anim_type = AnimationType(elem_data.get("animation_type", "pulse"))
                except ValueError:
                    anim_type = AnimationType.PULSE
                
                try:
                    easing = EasingFunction(elem_data.get("easing", "ease-in-out"))
                except ValueError:
                    easing = EasingFunction.EASE_IN_OUT
                
                elem = ElementAnimation(
                    selector=f"#{elem_data['element_id']}",
                    element_id=elem_data["element_id"],
                    element_type=elem_data.get("element_type", "node"),
                    animation_type=anim_type,
                    delay=elem_data.get("delay", 0.0),
                    duration=elem_data.get("duration", 2.0),
                    iterations=elem_data.get("iterations", -1),
                    direction=elem_data.get("direction", "alternate"),
                    easing=easing,
                    keyframes=keyframes,
                    fill_mode=elem_data.get("fill_mode", "both"),
                )
                elements.append(elem)
            
            seq = AnimationSequence(
                name=seq_data.get("name", "main"),
                description=seq_data.get("description", ""),
                elements=elements,
                parallel=seq_data.get("parallel", True),
                loop=seq_data.get("loop", True),
            )
            sequences.append(seq)
        
        return AnimationPlanV2(
            plan_id=_generate_plan_id(svg_id, data),
            svg_id=svg_id,
            diagram_type=diagram_type,
            description=data.get("description", "LLM-generated animation plan"),
            style=data.get("style", "default"),
            sequences=sequences,
            global_settings=data.get("global_settings", {}),
            metadata={"source": "llm", "model": "gpt-4o-mini"},
        )
    except Exception as e:
        print(f"Failed to parse LLM response: {e}")
        return None


def generate_animation_plan_llm(
    svg_text: str,
    svg_id: str = "svg-1",
    hint: Optional[str] = None,
) -> AnimationPlanV2:
    """
    Generate an intelligent animation plan using LLM.
    
    Args:
        svg_text: The SVG content to animate
        svg_id: Unique identifier for the SVG
        hint: Optional hint about diagram type or desired animation style
    
    Returns:
        AnimationPlanV2 object with animation configuration
    """
    # Analyze SVG structure
    structure = analyze_svg(svg_text, svg_id)
    structure_dict = structure.to_dict()
    
    # If no elements found, return empty plan
    if not structure.nodes and not structure.edges:
        return AnimationPlanV2(
            plan_id=f"plan-{svg_id}-empty",
            svg_id=svg_id,
            diagram_type="unknown",
            description="No animatable elements found",
            style="none",
            sequences=[],
        )
    
    # Try LLM generation
    prompt = ANIMATION_INTELLIGENCE_PROMPT.format(
        structure_json=json.dumps(structure_dict, indent=2),
        diagram_type=structure.diagram_type,
    )
    
    if hint:
        prompt += f"\n\nADDITIONAL HINT: {hint}"
    
    llm_response = _call_llm(prompt)
    
    if llm_response:
        plan = _parse_llm_response(llm_response, svg_id, structure.diagram_type)
        if plan:
            return plan
    
    # Fallback to default plan
    return create_default_plan(
        svg_id=svg_id,
        diagram_type=structure.diagram_type,
        nodes=[{"id": n.id} for n in structure.nodes],
        edges=[{"id": e.id} for e in structure.edges],
        groups=[{"id": g.id} for g in structure.groups],
    )


def tool_animation_intelligence(
    context: Dict[str, Any],
    svg_text: str,
    svg_id: str = "svg-1",
    hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    MCP tool handler for animation intelligence.
    
    Analyzes SVG structure and generates an intelligent animation plan.
    """
    try:
        plan = generate_animation_plan_llm(svg_text, svg_id, hint)
        return {
            "success": True,
            "plan": plan.to_dict(),
            "plan_json": plan.to_json(),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "plan": None,
        }


# Register the MCP tool
ANIMATION_INTELLIGENCE_TOOL = MCPTool(
    name="animation_intelligence_llm",
    description="Analyze SVG structure and generate an intelligent animation plan using LLM",
    input_schema={
        "type": "object",
        "properties": {
            "svg_text": {
                "type": "string",
                "description": "The SVG content to analyze and animate"
            },
            "svg_id": {
                "type": "string",
                "description": "Unique identifier for the SVG",
                "default": "svg-1"
            },
            "hint": {
                "type": "string",
                "description": "Optional hint about diagram type or desired animation style"
            }
        },
        "required": ["svg_text"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "plan": {"type": "object"},
            "plan_json": {"type": "string"},
            "error": {"type": "string"}
        }
    },
    side_effects="none",
    handler=tool_animation_intelligence,
)


def register_animation_tools():
    """Register animation-related MCP tools."""
    mcp_registry.register(ANIMATION_INTELLIGENCE_TOOL)


# Auto-register on import
register_animation_tools()
