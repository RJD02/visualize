#!/usr/bin/env python3
"""Generate animation verification report.

For each SVG under `.artifacts/ai-generated/<TS>/diagrams/svg`, apply
`src.animation_resolver.inject_animation` with `specs/presentation/example.json` and
verify that the animated SVG differs from the original only by injected <style>.

Writes `.artifacts/animation-verification-report.md`.
"""
import json
import os
from pathlib import Path
import sys

# add repo root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from animation_resolver import inject_animation, validate_presentation_spec
from xml.etree import ElementTree as ET

ARTIFACTS = Path(ROOT) / '.artifacts' / 'ai-generated'
OUT_REPORT = Path(ROOT) / '.artifacts' / 'animation-verification-report.md'
SPEC_PATH = Path(ROOT) / 'specs' / 'presentation' / 'example.json'

def find_latest_artifact_dir():
    if not ARTIFACTS.exists():
        return None
    dirs = [d for d in ARTIFACTS.iterdir() if d.is_dir()]
    if not dirs:
        return None
    dirs.sort(key=lambda p: p.name, reverse=True)
    return dirs[0]


def strip_style(svg_text: str) -> str:
    try:
        root = ET.fromstring(svg_text)
    except Exception:
        return svg_text
    # remove all <style> elements
    for style in list(root.findall('.//')):
        tag = style.tag
        if isinstance(tag, str) and tag.endswith('style'):
            parent = style.getparent() if hasattr(style, 'getparent') else None
            # ElementTree doesn't have getparent; we will rebuild by creating new tree
    # fallback: simple regex removal of <style> blocks
    import re
    return re.sub(r'<style[\s\S]*?<\/style>', '', svg_text, flags=re.IGNORECASE)


def normalize(s: str) -> str:
    return '\n'.join([line.strip() for line in s.splitlines() if line.strip()])


def main():
    latest = find_latest_artifact_dir()
    if not latest:
        print('No artifacts found under', ARTIFACTS)
        return 2
    svg_dir = latest / 'diagrams' / 'svg'
    if not svg_dir.exists():
        print('No svg directory at', svg_dir)
        return 2
    spec = {}
    if SPEC_PATH.exists():
        spec = json.loads(SPEC_PATH.read_text())
    else:
        print('Spec not found at', SPEC_PATH)
        return 2
    report_lines = []
    report_lines.append(f'# Animation verification report\n')
    report_lines.append(f'Artifacts: {latest}\n')
    report_lines.append('\n')
    passed = 0
    total = 0
    for svg_file in sorted(svg_dir.glob('*.svg')):
        total += 1
        svg_text = svg_file.read_text()
        try:
            valid, errors = validate_presentation_spec(svg_text, spec)
        except Exception as e:
            valid = False
            errors = [str(e)]
        if not valid:
            report_lines.append(f'## {svg_file.name} - FAILED validation')
            report_lines.append('\n')
            report_lines.append('\n'.join(['- ' + e for e in errors]))
            report_lines.append('\n')
            continue
        try:
            animated = inject_animation(svg_text, spec)
        except Exception as exc:
            report_lines.append(f'## {svg_file.name} - ERROR applying animation: {exc}')
            report_lines.append('\n')
            continue
        base = normalize(strip_style(svg_text))
        anim_no_style = normalize(strip_style(animated))
        only_style = (base == anim_no_style)
        if only_style:
            report_lines.append(f'## {svg_file.name} - PASS (only style injected)')
            passed += 1
        else:
            report_lines.append(f'## {svg_file.name} - FAIL (structural changes detected)')
            report_lines.append('\n')
            # show diff-ish info
            report_lines.append('--- original (stripped) ---')
            report_lines.append(base[:2000])
            report_lines.append('--- animated (stripped) ---')
            report_lines.append(anim_no_style[:2000])
        report_lines.append('\n')

    report_lines.append(f'\nTotal: {total}, Passed: {passed}, Failed: {total-passed}\n')
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text('\n'.join(report_lines))
    print('Wrote report to', OUT_REPORT)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
