"""Animation resolver: injects declarative CSS animations into SVG without changing structure.

Assumptions:
- PresentationSpec targets use simple selectors: #id, .class, or tag names. Complex selectors are partially supported.
- Animations are implemented in CSS and keyframes injected into an SVG <style> block.
"""
from typing import Dict, Any, List, Tuple
import re
from xml.etree import ElementTree as ET


SUPPORTED_TYPES = {"pulse", "draw", "fade", "highlight"}


def _find_by_simple_selector(root: ET.Element, selector: str) -> List[ET.Element]:
    # support #id, .class, tag
    if selector.startswith("#"):
        idv = selector[1:]
        return [e for e in root.iter() if e.get('id') == idv]
    if selector.startswith('.'):
        cls = selector[1:]
        return [e for e in root.iter() if (e.get('class') or '').split()].__class__()
    # tag name
    return list(root.iter(selector))


def _class_match_elements(root: ET.Element, class_name: str) -> List[ET.Element]:
    matches = []
    for e in root.iter():
        cls = e.get('class')
        if not cls:
            continue
        parts = re.split(r"\s+", cls.strip())
        if class_name in parts:
            matches.append(e)
    return matches


def validate_presentation_spec(svg_text: str, spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate selectors exist in SVG and animation types are supported.
    Returns (valid, errors)
    """
    errors = []
    try:
        root = ET.fromstring(svg_text)
    except Exception as exc:
        return False, [f"Invalid SVG: {exc}"]

    targets = spec.get('targets') or []
    for t in targets:
        sel = t.get('selector')
        if not sel:
            errors.append('Missing selector in target')
            continue
        elems = []
        if sel.startswith('#'):
            elems = _find_by_simple_selector(root, sel)
        elif sel.startswith('.'):
            elems = _class_match_elements(root, sel[1:])
        else:
            elems = list(root.iter(sel))
        if not elems:
            errors.append(f"Selector '{sel}' did not match any SVG elements")
        anim = t.get('animation')
        if anim:
            typ = anim.get('type')
            if typ not in SUPPORTED_TYPES:
                errors.append(f"Unsupported animation type: {typ}")

    return (len(errors) == 0), errors


def _gen_keyframe_name(selector: str, anim_type: str) -> str:
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', selector)
    return f"anim_{anim_type}_{safe}"


def _css_for_target(selector: str, target: Dict[str, Any]) -> str:
    styles = target.get('styles') or {}
    anim = target.get('animation')
    css_lines = []
    # styles
    if styles:
        decls = ';'.join(f"{k}:{v}" for k, v in styles.items())
        css_lines.append(f"{selector}{{{decls};}}")

    # animations
    if anim:
        typ = anim.get('type')
        dur = anim.get('duration', '1s')
        delay = anim.get('delay', '0s')
        easing = anim.get('easing', 'linear')
        repeat = anim.get('repeat', '1')
        kname = _gen_keyframe_name(selector, typ)
        if typ == 'pulse':
            css_lines.append(f"{selector}{{transform-origin:center;animation:{kname} {dur} {easing} {delay} {repeat};}}")
        elif typ == 'draw':
            css_lines.append(f"{selector}{{stroke-dasharray:1000;stroke-dashoffset:1000;animation:{kname} {dur} {easing} {delay} forwards;}}")
        elif typ == 'fade':
            css_lines.append(f"{selector}{{animation:{kname} {dur} {easing} {delay} {repeat};}}")
        elif typ == 'highlight':
            css_lines.append(f"{selector}{{animation:{kname} {dur} {easing} {delay} {repeat};}}")

    return '\n'.join(css_lines)


def _keyframes_for_target(selector: str, target: Dict[str, Any]) -> str:
    anim = target.get('animation')
    if not anim:
        return ''
    typ = anim.get('type')
    kname = _gen_keyframe_name(selector, typ)
    if typ == 'pulse':
        return f"@keyframes {kname} {{0% {{transform: scale(1); opacity:1}}50% {{transform: scale(1.06); opacity:0.85}}100% {{transform: scale(1); opacity:1}}}}"
    if typ == 'draw':
        return f"@keyframes {kname} {{0% {{stroke-dashoffset:1000}}100% {{stroke-dashoffset:0}}}}"
    if typ == 'fade':
        return f"@keyframes {kname} {{0% {{opacity:0}}100% {{opacity:1}}}}"
    if typ == 'highlight':
        return f"@keyframes {kname} {{0% {{filter: drop-shadow(0 0 0 rgba(0,0,0,0))}}50% {{filter: drop-shadow(0 0 6px rgba(255,255,0,0.8))}}100% {{filter: drop-shadow(0 0 0 rgba(0,0,0,0))}}}}"
    return ''


def inject_animation(svg_text: str, spec: Dict[str, Any]) -> str:
    """Return new svg text with injected <style> including keyframes and rules.

    Does not modify existing elements or attributes (except adding nothing). We only inject <style>.
    """
    valid, errors = validate_presentation_spec(svg_text, spec)
    if not valid:
        raise ValueError('; '.join(errors))

    try:
        root = ET.fromstring(svg_text)
    except Exception as exc:
        raise ValueError(f"Invalid SVG: {exc}")

    # build CSS
    css_parts: List[str] = []
    keyframes_parts: List[str] = []
    for t in spec.get('targets', []):
        sel = t.get('selector')
        if sel.startswith('.'):
            sel_css = f".{sel[1:]}"
        else:
            sel_css = sel
        css = _css_for_target(sel_css, t)
        kf = _keyframes_for_target(sel_css, t)
        if css:
            css_parts.append(css)
        if kf:
            keyframes_parts.append(kf)

    full_css = '\n'.join(keyframes_parts + css_parts)

    # inject into or create <style> inside SVG
    # find existing <style>
    style_elem = None
    for e in root.findall('.//'):
        tag = e.tag
        if isinstance(tag, str) and tag.endswith('style'):
            style_elem = e
            break
    if style_elem is None:
        # create style element as first child
        style_elem = ET.Element('style')
        style_elem.text = '\n' + full_css + '\n'
        root.insert(0, style_elem)
    else:
        style_elem.text = (style_elem.text or '') + '\n' + full_css + '\n'

    return ET.tostring(root, encoding='unicode')
