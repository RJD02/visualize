#!/usr/bin/env python3
"""Test animation rendering."""
from src.animation.diagram_renderer import render_svg_v2
from pathlib import Path

svg_path = list(Path('outputs').glob('*container*.svg'))[0]
svg_text = svg_path.read_text()
animated = render_svg_v2(svg_text)

html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Animation Test</title>
    <style>
        body {{ background: #0f172a; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
        .container {{ background: #1e293b; padding: 20px; border-radius: 8px; max-width: 95vw; overflow: auto; }}
    </style>
</head>
<body>
    <div class="container">
        {animated}
    </div>
</body>
</html>"""

output_path = Path('ui/animation_test_output.html')
output_path.write_text(html)
print(f'✓ Created {output_path}')
print(f'✓ Open http://localhost:5173/animation_test_output.html to test')
