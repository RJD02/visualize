import pytest
from src.diagram import icon_injector


SAMPLE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
  <g id="node-1"><rect x="10" y="10" width="50" height="30"/></g>
  <g id="node-2"><rect x="70" y="10" width="50" height="30"/></g>
</svg>'''


def test_mapping_resolution():
    mapping = {"node-1": "postgres", "node-2": "kafka"}
    out = icon_injector.inject_icons(SAMPLE_SVG, mapping)
    assert "icon-postgres" in out
    assert "icon-kafka" in out


def test_idempotence():
    mapping = {"node-1": "postgres"}
    out1 = icon_injector.inject_icons(SAMPLE_SVG, mapping)
    out2 = icon_injector.inject_icons(out1, mapping)
    # injected marker should prevent double injection
    assert out2.count('data-icon-injected') == 1


def test_missing_icon_fallback():
    mapping = {"node-1": "unknown-service"}
    out = icon_injector.inject_icons(SAMPLE_SVG, mapping)
    # should fallback to service-generic symbol id
    assert "icon-unknown-service" not in out
    # generic symbol id should be present
    assert "icon-service-generic" in out


def test_duplicate_unknowns_use_single_generic_symbol():
    # two different unknown tokens should not create multiple generic symbols
    sample = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
  <g id="n1"></g>
  <g id="n2"></g>
</svg>'''
    mapping = {"n1": "foo", "n2": "bar"}
    out = icon_injector.inject_icons(sample, mapping)
    # only one generic symbol should be present
    assert out.count('symbol id="icon-service-generic"') == 1


def test_use_attributes_present():
    mapping = {"node-1": "postgres"}
    out = icon_injector.inject_icons(SAMPLE_SVG, mapping)
    # ensure both href and xlink:href appear in the injected use element
    import xml.etree.ElementTree as ET
    root = ET.fromstring(out)
    # find g with id=node-1 and its first child use
    use_el = None
    for g in root.iter():
        if g.attrib.get('id') == 'node-1':
            for child in list(g):
                if child.tag.endswith('use'):
                    use_el = child
                    break
            break
    assert use_el is not None
    # check regular href
    assert use_el.attrib.get('href') == '#icon-postgres' or use_el.attrib.get('{http://www.w3.org/1999/xlink}href') == '#icon-postgres'


# ---------------------------------------------------------------------------
# BUG-BLUE-DOT regression guard tests
# ---------------------------------------------------------------------------

_BLUE_CIRCLE_PATH = "M12 2a10 10 0 100 20A10 10 0 0012 4z"


def test_known_service_does_not_render_circle_path():
    """BUG-BLUE-DOT: known brand icons must not embed the generic blue circle path."""
    for token in ("kafka", "postgres"):
        out = icon_injector.inject_icons(SAMPLE_SVG, {"node-1": token})
        assert _BLUE_CIRCLE_PATH not in out, (
            f"Generic blue circle path found in output for '{token}' icon — "
            "brand SVG should not contain the circle fallback path"
        )


def test_unknown_service_fallback_is_not_blue_circle():
    """BUG-BLUE-DOT: unknown services fall back to service-generic which must not contain the blue circle."""
    out = icon_injector.inject_icons(SAMPLE_SVG, {"node-1": "completely-unknown-xyz-service"})
    assert "icon-service-generic" in out, "Fallback symbol id not found in output"
    assert _BLUE_CIRCLE_PATH not in out, (
        "Blue circle path found in generic fallback SVG — "
        "service-generic.svg must not embed the client-side blue circle path"
    )


def test_resolve_icon_key_covers_all_mapping_keys():
    """BUG-BLUE-DOT: every MAPPING key must be self-resolvable, and _KEYWORDS must have ≥ 30 entries."""
    from src.diagram.icon_injector import MAPPING, _KEYWORDS, resolve_icon_key

    # At least 30 keyword entries must exist
    assert len(_KEYWORDS) >= 30, (
        f"Only {len(_KEYWORDS)} keywords defined — acceptance requires ≥ 30"
    )

    # Every MAPPING key is reachable: resolve_icon_key(key) should return that key
    for key in MAPPING:
        result = resolve_icon_key(key)
        assert result == key, (
            f"resolve_icon_key('{key}') returned {result!r}; "
            f"a keyword entry for '{key}' must exist in _KEYWORDS"
        )


def test_inject_icons_idempotent_symbol_count():
    """BUG-BLUE-DOT: injecting the same map twice must not duplicate symbols in the sprite."""
    import re
    mapping = {"node-1": "postgres", "node-2": "kafka"}
    out1 = icon_injector.inject_icons(SAMPLE_SVG, mapping)
    out2 = icon_injector.inject_icons(out1, mapping)
    kafka_count = len(re.findall(r'symbol id="icon-kafka"', out2))
    postgres_count = len(re.findall(r'symbol id="icon-postgres"', out2))
    assert kafka_count == 1, f"icon-kafka symbol duplicated after second inject: found {kafka_count}"
    assert postgres_count == 1, f"icon-postgres symbol duplicated after second inject: found {postgres_count}"
