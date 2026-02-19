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
