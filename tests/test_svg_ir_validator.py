import json

from src.models.architecture_plan import ArchitecturePlan
from src.tools.ir_validator import IRValidationError, validate_svg_ir
from src.tools.svg_ir import build_ir_from_plan, ir_to_svg


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


def test_ir_validator_accepts_generated_svg():
    plan = ArchitecturePlan.model_validate(_plan())
    ir = build_ir_from_plan(plan, "system_context")
    svg = ir_to_svg(ir)
    validate_svg_ir(svg)


def test_ir_validator_rejects_animation():
    bad_svg = """
    <svg xmlns='http://www.w3.org/2000/svg'>
      <g id='node_a' data-kind='node' data-role='service'>
        <rect id='node_a_rect' width='10' height='10'/>
      </g>
      <animate attributeName='x' />
    </svg>
    """
    try:
        validate_svg_ir(bad_svg)
        assert False, "Expected validation error"
    except IRValidationError as exc:
        assert "Animation" in str(exc)


def test_ir_validator_rejects_missing_group_metadata():
    bad_svg = """
    <svg xmlns='http://www.w3.org/2000/svg'>
      <g id='node_a'>
        <rect id='node_a_rect' width='10' height='10'/>
      </g>
    </svg>
    """
    try:
        validate_svg_ir(bad_svg)
        assert False, "Expected validation error"
    except IRValidationError as exc:
        assert "data-kind" in str(exc)


def test_ir_validator_rejects_hex_color():
    bad_svg = """
    <svg xmlns='http://www.w3.org/2000/svg'>
      <style>.node{fill:#ff00ff;}</style>
      <g id='node_a' data-kind='node' data-role='service'>
        <rect id='node_a_rect' width='10' height='10' fill='#ff00ff'/>
      </g>
    </svg>
    """
    try:
        validate_svg_ir(bad_svg)
        assert False, "Expected validation error"
    except IRValidationError as exc:
        assert "Disallowed hex color" in str(exc)
