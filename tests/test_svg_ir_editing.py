import xml.etree.ElementTree as ET

from src.models.architecture_plan import ArchitecturePlan
from src.tools.svg_ir import build_ir_from_plan, ir_to_svg, edit_ir_svg


def _plan():
    return {
        "system_name": "Test System",
        "diagram_views": ["system_context"],
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


def _node_ids(svg_text: str) -> set[str]:
    root = ET.fromstring(svg_text)
    ids = set()
    for elem in root.iter():
        if elem.attrib.get("data-kind") == "node":
            ids.add(elem.attrib.get("id"))
    return ids


def test_deterministic_render_output():
    plan = ArchitecturePlan.model_validate(_plan())
    svg1 = ir_to_svg(build_ir_from_plan(plan, "system_context"))
    svg2 = ir_to_svg(build_ir_from_plan(plan, "system_context"))
    assert svg1 == svg2


def test_edit_preserves_stable_ids():
    plan = ArchitecturePlan.model_validate(_plan())
    svg = ir_to_svg(build_ir_from_plan(plan, "system_context"))
    edited = edit_ir_svg(svg, "move core_services above edge")
    assert _node_ids(svg) == _node_ids(edited)
