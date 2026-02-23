import re
from pathlib import Path

# default assets dir (local, deterministic)
ASSETS_DIR = Path(__file__).resolve().parents[1] / "icons" / "assets"




def inject_svg(svg_text: str) -> str:
    """Normalize an inline SVG string for injection into node containers.

    - Removes explicit width/height attributes to allow flexible scaling.
    - Ensures a viewBox exists (defaults to 0 0 24 24 if missing).
    - Preserves path/g/group elements.

    This is intentionally minimal and deterministic to avoid layout shifts.
    """
    if svg_text is None:
        return ""

    # Remove width/height attributes (both single and double quoted)
    svg = re.sub(r"\s(width|height)=(\"[^\"]*\"|'[^']*')", "", svg_text, flags=re.IGNORECASE)

    # If viewBox missing, add a default one to allow scaling
    if "viewBox" not in svg:
        # try to detect numeric width/height if present previously (best-effort)
        # fallback to 0 0 24 24
        default = "0 0 24 24"
        svg = re.sub(r"<svg(\s|>)", f"<svg viewBox=\"{default}\" ", svg, count=1)

    # Ensure at least one path or shape remains; we do not strip elements here
    return svg


def has_visible_path(svg_text: str) -> bool:
    """Return True if the svg contains at least one non-empty path/rect/circle element."""
    if not svg_text:
        return False
    return bool(re.search(r"<(path|rect|circle|ellipse|polygon)\b", svg_text, flags=re.IGNORECASE))


def inline_use_references(svg_text: str) -> str:
    """Replace <use href="#id"> references with the corresponding <symbol> content in the same document.

    This inlining guarantees that icons are present as concrete shapes (no <use> dependency on <defs>),
    which improves rendering determinism across embedding methods.
    """
    if not svg_text:
        return svg_text

    # find all symbols and their inner content
    symbols = {}
    # naive regex extraction: captures symbol start tag with id and inner HTML until </symbol>
    for m in re.finditer(r"<(?:\w+:)?symbol[^>]*\s+id=[\"']([^\"']+)[\"'][^>]*>(.*?)</(?:\w+:)?symbol>", svg_text, flags=re.DOTALL | re.IGNORECASE):
        sid = m.group(1)
        inner = m.group(2)
        symbols[sid] = inner

    def load_asset_inline(idpart: str):
        # map symbol id like 'icon-postgres' -> 'postgres.svg'
        name = idpart.replace('icon-', '')
        path = ASSETS_DIR / f"{name}.svg"
        if path.exists():
            try:
                txt = path.read_text(encoding='utf-8')
                # extract inner children of <svg>...</svg>
                m = re.search(r"<svg[^>]*>(.*?)</svg>", txt, flags=re.DOTALL | re.IGNORECASE)
                if m:
                    return m.group(1)
                return txt
            except Exception:
                return None
        return None


    def replace_use(match):
        raw = match.group(0)
        ref = match.group(1)
        # extract id part
        idpart = ref.split('#')[-1] if '#' in ref else ref
        # prefer local asset when available, otherwise use symbol content
        inner = load_asset_inline(idpart) or symbols.get(idpart)
        if inner:
            # preserve class attribute if present
            cls = ''
            mcls = re.search(r"class=[\"']([^\"']+)[\"']", raw)
            if mcls:
                cls = f' class="{mcls.group(1)}"'
            return f'<g{cls} data-inlined-from="{idpart}">{inner}</g>'
        return raw

    # replace <use ... href="..."> tags
    result = re.sub(r"<(?:\w+:)?use[^>]*(?:href|xlink:href)=[\"']([^\"']+)[\"'][^>]*/?>", replace_use, svg_text, flags=re.IGNORECASE)
    # Normalize styles that may hide inlined icons when SVG is used standalone.
    return _normalize_icon_styles(result)


def _normalize_icon_styles(svg_text: str) -> str:
    """Remove or neutralize CSS rules that hide icon groups when SVG is rendered standalone.

    - Removes style rules that set opacity:0 or display:none for selectors targeting
      `.node-icon`, `.injected-icon` or their `.hidden` variants.
    - If a <style> block becomes empty after removals, the block is removed entirely.
    This keeps other unrelated styles intact when possible.
    """
    if not svg_text:
        return svg_text

    # Regex that matches opacity:0 exactly (not opacity:0.5, opacity:0.92, etc.)
    _HIDDEN_DECL = re.compile(
        r'opacity\s*:\s*0(?:[^.\d]|$)|display\s*:\s*none|visibility\s*:\s*hidden',
        re.IGNORECASE,
    )
    _ICON_SEL = re.compile(r'\.node-icon|\.injected-icon', re.IGNORECASE)

    def _clean_style_block(m):
        opening_tag = m.group(0)[:m.group(0).index('>') + 1]  # preserve attrs like id=
        content = m.group(1)
        parts = [p.strip() for p in content.split('}') if p.strip()]
        kept = []
        for part in parts:
            if '{' not in part:
                continue
            sel, decl = part.split('{', 1)
            sel = sel.strip()
            decl = decl.strip()
            # Drop rules that target icon selectors AND explicitly hide them (opacity:0 etc.)
            if _ICON_SEL.search(sel) and _HIDDEN_DECL.search(decl):
                continue
            kept.append(f"{sel} {{{decl}}}")
        if not kept:
            return ''
        return opening_tag + '\n'.join(kept) + '</style>'

    # replace all <style...>...</style> occurrences
    result = re.sub(r"<style[^>]*>(.*?)</style>", lambda m: _clean_style_block(m), svg_text, flags=re.DOTALL | re.IGNORECASE)
    # neutralize any remaining standalone opacity:0/display:none that would hide inlined icons
    # Use word-boundary-aware replacements to avoid corrupting values like opacity:0.5
    result = re.sub(r'\bopacity\s*:\s*0(?=[^.\d])', 'opacity:1', result)
    result = result.replace('visibility:hidden', 'visibility:visible')
    result = result.replace('display:none', 'display:block')
    # ensure default SVG namespace exists so unprefixed inlined elements render correctly
    return _ensure_default_svg_namespace(result)


def _ensure_default_svg_namespace(svg_text: str) -> str:
    """Add a default xmlns="http://www.w3.org/2000/svg" to the root svg tag if missing.

    Some generated SVGs use a prefixed root element (e.g., <ns0:svg ...>) without a default
    namespace. Browsers treat unprefixed inlined children as non-SVG elements unless a default
    xmlns is present, causing getBBox() to return zero. This function inserts the default
    xmlns attribute when needed.
    """
    if not svg_text:
        return svg_text
    # if default xmlns already present, nothing to do
    if 'xmlns="http://www.w3.org/2000/svg"' in svg_text:
        return svg_text
    # if root uses a namespaced svg like <ns0:svg, add default xmlns after the tag name
    m = re.search(r"<([a-zA-Z0-9_]+:svg)(\b[^>]*)", svg_text)
    if m:
        full = m.group(0)
        tag = m.group(1)
        rest = m.group(2)
        # replace the prefixed root tag with an unprefixed 'svg' tag and add default xmlns
        new = f"<svg xmlns=\"http://www.w3.org/2000/svg\"{rest}"
        out = svg_text.replace(full, new, 1)
        # also replace the corresponding closing tag (e.g., </ns0:svg>) with </svg>
        out = re.sub(r"</[a-zA-Z0-9_]+:svg>", "</svg>", out, count=1)
        return out
    # fallback: add default xmlns to any <svg tag
    svg_text = re.sub(r"<svg(\b[^>]*)", r"<svg xmlns=\"http://www.w3.org/2000/svg\"\1", svg_text, count=1)
    return svg_text

if __name__ == "__main__":
    # quick local smoke test
    sample = '<svg width="48" height="48"><path d="M0 0h24v24H0z"/></svg>'
    print(inject_svg(sample))
