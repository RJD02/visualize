import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from animation_resolver import inject_animation, validate_presentation_spec

ARTIFACTS = ROOT / '.artifacts' / 'ai-generated'
SPEC = ROOT / 'specs' / 'presentation' / 'example.json'


def find_latest():
    if not ARTIFACTS.exists():
        return None
    dirs = [d for d in ARTIFACTS.iterdir() if d.is_dir()]
    if not dirs:
        return None
    dirs.sort(key=lambda p: p.name, reverse=True)
    return dirs[0]


def strip_style(svg: str) -> str:
    import re
    return re.sub(r'<style[\s\S]*?<\/style>', '', svg, flags=re.IGNORECASE).strip()


def test_animated_only_injects_style():
    latest = find_latest()
    assert latest is not None
    svg_dir = latest / 'diagrams' / 'svg'
    assert svg_dir.exists()
    spec = json.loads(SPEC.read_text())

    for svg_path in sorted(svg_dir.glob('*.svg')):
        svg_text = svg_path.read_text()
        valid, errors = validate_presentation_spec(svg_text, spec)
        # if spec doesn't match this svg, skip
        if not valid:
            continue
        animated = inject_animation(svg_text, spec)
        assert strip_style(svg_text) == strip_style(animated), f"Structural change detected in {svg_path.name}"

