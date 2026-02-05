#!/usr/bin/env python3
"""Generate an HTML test file with animated SVG."""
from src.animation.diagram_renderer import render_svg_v2

with open('outputs/0ba8fd06-c00e-48b3-93ad-99c989a3b6ad_container_2.svg') as f:
    svg_text = f.read()

animated = render_svg_v2(svg_text)

# Create HTML wrapper for better viewing
html = """<!DOCTYPE html>
<html>
<head>
    <title>SVG Animation Test (with Text)</title>
    <style>
        body {
            background: #1a1a2e;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
        }
        .svg-container {
            max-width: 90vw;
            max-height: 90vh;
            overflow: auto;
        }
        svg {
            max-width: 100%;
            height: auto;
        }
    </style>
</head>
<body>
    <div class="svg-container">
""" + animated + """
    </div>
</body>
</html>"""

with open('ui/animation_test_with_text.html', 'w') as f:
    f.write(html)

print('Created: ui/animation_test_with_text.html')
print('Open this file in a browser to see both rect and text animations!')
