import re

from src.models.architecture_plan import ArchitecturePlan
from src.tools.svg_ir import build_ir_from_plan, ir_to_svg
from src.tools.ir_renderer import render_ir


def _plan():
    return {
        "system_name": "Test System",
        "diagram_views": ["system_context", "container"],
        "zones": {
            "clients": ["Client"],
            "edge": ["Gateway"],
            "core_services": ["Service"],
            "external_services": ["External"],
            "data_stores": ["DB"],
        },
        "relationships": [
            {"from": "Client", "to": "Gateway", "type": "sync", "description": "call"}
        ],
        "visual_hints": {
            "layout": "top-down",
            "group_by_zone": True,
            "external_dashed": True,
        },
    }


def test_image_only_output_has_title():
    plan = ArchitecturePlan.model_validate(_plan())
    svg = ir_to_svg(build_ir_from_plan(plan, "system_context"))
    assert "<svg" in svg
    assert "C4 Context Diagram" in svg
    assert "@startuml" not in svg
    assert "{" not in svg or "metadata" in svg


def test_deterministic_regeneration():
    plan = ArchitecturePlan.model_validate(_plan())
    svg1 = ir_to_svg(build_ir_from_plan(plan, "system_context"))
    svg2 = ir_to_svg(build_ir_from_plan(plan, "system_context"))
    assert svg1 == svg2


def test_renderer_swap_safety():
    plan = ArchitecturePlan.model_validate(_plan())
    ir = build_ir_from_plan(plan, "system_context")
    svg_out = render_ir(ir, "svg")["svg"]
    plantuml_out = render_ir(ir, "plantuml")["svg"]
    mermaid_out = render_ir(ir, "mermaid")["svg"]

    assert svg_out == plantuml_out == mermaid_out
    assert "<svg" in svg_out


def test_diagram_type_labeling():
    plan = ArchitecturePlan.model_validate(_plan())
    svg = ir_to_svg(build_ir_from_plan(plan, "container"))
    assert "C4 Container Diagram" in svg


def test_no_ir_leakage_in_text():
    plan = ArchitecturePlan.model_validate(_plan())
    svg = ir_to_svg(build_ir_from_plan(plan, "system_context"))
    # Ensure no PlantUML or Mermaid syntax present
    assert "@startuml" not in svg
    assert "sequenceDiagram" not in svg