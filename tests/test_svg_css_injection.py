from src.animation.diagram_renderer import render_svg


def test_render_svg_injects_style():
    svg = """
<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"200\" height=\"100\">
  <g>
    <rect x=\"10\" y=\"10\" width=\"60\" height=\"20\" />
    <text x=\"20\" y=\"25\">step1 User</text>
  </g>
  <path d=\"M70 20 L120 20\" stroke=\"#000\" />
</svg>
""".strip()
    out = render_svg(svg, animated=True)
    assert "<style" in out
    assert "animNodePulse" in out
    assert "animEdgeFlow" in out


def test_render_svg_debug_injects_blink():
    svg = "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>"
    out = render_svg(svg, animated=True, debug=True)
    assert "debugBlink" in out


def test_render_svg_static_unchanged():
    svg = "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>"
    out = render_svg(svg, animated=False)
    assert out == svg
