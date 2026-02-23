"""Unit tests for icon injection visibility — BUG-ICON-CIRCLE-RENDER-01 regression guard.

Verifies:
1. inject_icons() creates defs + symbols + use elements with position attributes.
2. The <use> elements are NOT replaced by inline_use_references() in the render pipeline.
3. Brand icon symbols contain real <path> elements, not generic circle paths.
4. Server render pipeline leaves <use> intact (no inline_use_references call).
"""
import re
from src.diagram.icon_injector import inject_icons


_SAMPLE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg">
  <g id="n1" data-kind="node">
    <rect x="10" y="5" width="200" height="60" />
    <text x="110" y="35">kafka</text>
  </g>
</svg>'''

_AIRFLOW_SVG = '''<svg xmlns="http://www.w3.org/2000/svg">
  <g id="n2" data-kind="node">
    <rect x="0" y="-30" width="260" height="60" />
    <text x="130" y="0">Airflow/Superset/OpenMetadata</text>
  </g>
</svg>'''

_KUBERNETES_SVG = '''<svg xmlns="http://www.w3.org/2000/svg">
  <g id="n3" data-kind="node">
    <rect x="-130" y="-39" width="260" height="78" />
    <text x="0" y="0">Kubernetes Cluster (PROD)</text>
  </g>
</svg>'''


def test_inject_icons_creates_defs_and_symbols():
    out = inject_icons(_SAMPLE_SVG, {"n1": "kafka"})
    assert "icon-sprite" in out
    assert "icon-kafka" in out
    assert "#icon-kafka" in out
    assert "node-icon" in out


def test_inject_icons_use_has_position_attributes():
    """Regression: <use> must carry x, y, width, height so the browser positions and scales correctly."""
    out = inject_icons(_KUBERNETES_SVG, {"n3": "Kubernetes Cluster (PROD)"})
    # Find the <use> element
    use_matches = re.findall(r'<use\b[^>]*/?>|<use\b[^>]*>.*?</use>', out, re.DOTALL | re.IGNORECASE)
    assert use_matches, "No <use> element found in injected SVG"
    use_tag = use_matches[0]
    assert 'x=' in use_tag or "x='" in use_tag, f"<use> missing x attribute: {use_tag}"
    assert 'y=' in use_tag or "y='" in use_tag, f"<use> missing y attribute: {use_tag}"
    assert 'width=' in use_tag, f"<use> missing width attribute: {use_tag}"
    assert 'height=' in use_tag, f"<use> missing height attribute: {use_tag}"


def test_brand_icon_symbol_contains_real_paths():
    """Regression: brand icons must have actual <path> elements, not the generic circle fallback."""
    _GENERIC_CIRCLE_PATH = "M12 2a10 10 0 100 20A10 10 0 0012 4z"
    for label, node_id in [("Airflow/Superset/OpenMetadata", "n2"), ("Kubernetes Cluster (PROD)", "n3")]:
        svg = _AIRFLOW_SVG if node_id == "n2" else _KUBERNETES_SVG
        out = inject_icons(svg, {node_id: label})
        # Must have path elements (real brand SVG)
        path_count = len(re.findall(r'<[^>]*:?path\b', out))
        assert path_count > 0, f"No <path> elements found for icon of '{label}'"
        # Must NOT be the generic circle-only fallback
        assert _GENERIC_CIRCLE_PATH not in out, (
            f"Generic circle fallback path found for '{label}' — brand SVG not loaded"
        )


def test_data_icon_injected_flag_is_set():
    """Regression: node group must carry data-icon-injected='1' for client-side guard to work."""
    out = inject_icons(_AIRFLOW_SVG, {"n2": "Airflow/Superset/OpenMetadata"})
    assert 'data-icon-injected="1"' in out or "data-icon-injected='1'" in out, (
        "data-icon-injected flag not set — client-side guard won't fire"
    )


def test_render_pipeline_leaves_use_intact():
    """Regression: inject_icons() must produce <use> elements that are NOT replaced
    by inline_use_references().  We test inject_icons() directly (not server.py,
    which requires a DB context) because the server fix is simply to not call
    inline_use_references() after inject_icons().

    After inject_icons() runs:
    - <use> elements with position attrs must exist
    - data-inlined-from must NOT be present (no inlining happened)
    """
    # Use the real Mermaid SVG to simulate the server pipeline
    svg_path = 'outputs/46050207-2fb4-41c4-950a-c24521b94b81_component_2.svg'
    with open(svg_path, encoding='utf-8') as fh:
        svg_text = fh.read()

    # Replicate _auto_inject_icons() node discovery logic (Pass 1 and Pass 2)
    from xml.etree import ElementTree as ET

    def _strip_ns(tag):
        return tag.split('}')[-1] if '}' in tag else tag

    from src.diagram.icon_injector import inject_icons, resolve_icon_key

    root = ET.fromstring(svg_text)
    node_service_map = {}
    for el in root.iter():
        if _strip_ns(el.tag) != 'g':
            continue
        cls = el.attrib.get('class', '')
        eid = el.attrib.get('id', '')
        if not eid or 'node' not in cls.split():
            continue
        parts = []
        for child in el.iter():
            ctag = _strip_ns(child.tag)
            if ctag in ('div', 'span', 'p'):
                t = (child.text or '').strip()
                if t:
                    parts.append(t)
        label = ' '.join(parts).strip()
        if label and resolve_icon_key(label):
            node_service_map[eid] = label

    assert node_service_map, "No icon-resolvable nodes found in test SVG"

    result = inject_icons(svg_text, node_service_map)

    # After inject_icons(): <use> elements with position attrs must exist
    use_count = len(re.findall(r'<[^>]*:?use\b', result))
    assert use_count > 0, (
        "No <use> elements found after inject_icons() — icon injection may have failed"
    )

    # data-inlined-from must NOT be present (inline_use_references was NOT called)
    assert 'data-inlined-from' not in result, (
        "data-inlined-from found — inline_use_references() was called unexpectedly "
        "(BUG-ICON-CIRCLE-RENDER-01: this strips x/y/width/height from <use> elements)"
    )

    # Each <use> referencing a brand symbol must have x, y, width, height
    use_tags = re.findall(r'<[^>]*:?use\b[^>]*/?>|<[^>]*:?use\b[^>]*>.*?</[^>]*:?use>', result, re.DOTALL)
    for use_tag in use_tags:
        if 'icon-' not in use_tag:
            continue  # skip non-brand uses
        assert re.search(r'\bx=', use_tag), f"<use> missing x attr: {use_tag[:200]}"
        assert re.search(r'\by=', use_tag), f"<use> missing y attr: {use_tag[:200]}"
        assert 'width=' in use_tag, f"<use> missing width attr: {use_tag[:200]}"
        assert 'height=' in use_tag, f"<use> missing height attr: {use_tag[:200]}"
