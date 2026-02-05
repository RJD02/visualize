#!/usr/bin/env python3
"""Test script to debug SVG animation parsing."""

import re
from pathlib import Path
from src.animation.svg_parser import parse_svg
from src.animation.animation_plan_generator import generate_animation_plan
from src.animation.diagram_renderer import render_svg

# Test with real SVG file
svg_path = Path("outputs/0ba8fd06-c00e-48b3-93ad-99c989a3b6ad_system_context_1.svg")
if svg_path.exists():
    svg = svg_path.read_text()
    print("=== TESTING WITH REAL SVG FILE ===")
else:
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="720">
<g id="node_gateway" data-kind="node"><rect class="node-rect" x="40" y="180"/><text class="node-text">Gateway</text></g>
<g id="node_service" data-kind="node"><rect class="node-rect" x="40" y="300"/><text class="node-text">Service</text></g>
<line id="edge_line_1" class="edge-line" x1="180" y1="84" x2="160" y2="84"/>
</svg>'''
    print("=== TESTING WITH INLINE SVG ===")

parsed = parse_svg(svg)
print('\n=== NODES (first 5) ===')
for n in parsed.nodes[:5]:
    el_id = n.element.get("id")
    print(f'  label={n.label!r}, selector={n.selector!r}, el_id={el_id!r}')

print('\n=== EDGES (first 5) ===')  
for e in parsed.edges[:5]:
    el_id = e.element.get("id")
    print(f'  selector={e.selector!r}, el_id={el_id!r}')

plan = generate_animation_plan(parsed)
print('\n=== ANIMATION PLAN (first 5 steps) ===')
for s in plan.steps[:5]:
    print(f'  selector={s.selector!r}, role={s.role}')

print('\n=== RENDERED SVG WITH ANIMATION (CSS section) ===')
animated = render_svg(svg, animated=True, debug=True)

# Extract and print only the style element
style_match = re.search(r'<style>(.*?)</style>', animated, re.DOTALL)
if style_match:
    print(style_match.group(0)[:2500])
else:
    print("No <style> element found!")

# Create test HTML file
html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Animated SVG Test</title>
    <style>
        body { background: #1e293b; padding: 20px; }
        h1 { color: white; font-family: sans-serif; }
        p { color: #94a3b8; font-family: sans-serif; }
    </style>
</head>
<body>
    <h1>Animated SVG Test - Should be blinking/pulsing</h1>
    <p>If you see elements fading in and out, animations are working!</p>
    """ + animated + """
</body>
</html>"""

output_path = Path("ui/animated_test_output.html")
output_path.write_text(html_content)
print(f'\n=== Created {output_path} ===')
print('Open this file in a browser to verify animations work.')
