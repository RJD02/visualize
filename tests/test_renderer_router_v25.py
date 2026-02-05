from src.renderers.renderer_ir import RendererIR, IRNode, IREdge
from src.renderers.router import choose_renderer
from src.renderers.neutral_svg import strip_svg_colors, validate_neutral_svg
from src.animation.diagram_renderer import render_svg


def _sample_ir(kind: str = "flow") -> RendererIR:
    return RendererIR(
        diagram_kind=kind,
        layout="top-down",
        nodes=[
            IRNode(id="user", kind="person"),
            IRNode(id="api", kind="service"),
            IRNode(id="db", kind="database"),
        ],
        edges=[
            IREdge(**{"from": "user", "to": "api", "type": "interaction"}),
            IREdge(**{"from": "api", "to": "db", "type": "data-flow"}),
        ],
    )


def test_router_selects_mermaid_for_flow():
    choice = choose_renderer(_sample_ir("flow"))
    assert choice.renderer == "mermaid"


def test_router_selects_structurizr_for_architecture():
    choice = choose_renderer(_sample_ir("architecture"))
    assert choice.renderer == "structurizr"


def test_neutral_svg_strip_and_validate():
    svg = """
    <svg xmlns='http://www.w3.org/2000/svg'>
      <style>.node{fill:#ff00ff;}</style>
      <rect id='a' fill='#ff00ff' stroke='red'/>
    </svg>
    """
    stripped = strip_svg_colors(svg)
    validate_neutral_svg(stripped)


def test_post_svg_compatibility():
    svg = """
    <svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>
      <g id='node_a' data-kind='node' data-role='service'>
        <rect id='node_a_rect' x='10' y='10' width='80' height='30'/>
        <text id='node_a_text' x='15' y='30'>A</text>
      </g>
    </svg>
    """
    enhanced = render_svg(svg, animated=False, enhanced=True)
    assert isinstance(enhanced, str)
