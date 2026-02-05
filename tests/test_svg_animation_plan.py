from src.animation.svg_parser import parse_svg
from src.animation.animation_plan_generator import generate_animation_plan


def _simple_svg() -> str:
    return """
<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"200\" height=\"100\">
  <g>
    <rect x=\"10\" y=\"10\" width=\"60\" height=\"20\" />
    <text x=\"20\" y=\"25\">step1 User</text>
  </g>
  <g>
    <rect x=\"120\" y=\"10\" width=\"60\" height=\"20\" />
    <text x=\"130\" y=\"25\">step2 API</text>
  </g>
  <path d=\"M70 20 L120 20\" stroke=\"#000\" />
</svg>
""".strip()


def test_animation_plan_orders_steps():
    parsed = parse_svg(_simple_svg())
    plan = generate_animation_plan(parsed)
    assert len(plan.steps) >= 2
    assert plan.steps[0].role == "node"
    assert plan.steps[0].selector.startswith("#") or plan.steps[0].selector.startswith(".")


def test_plan_has_edge_step():
    parsed = parse_svg(_simple_svg())
    plan = generate_animation_plan(parsed)
    assert any(step.role == "edge" for step in plan.steps)
