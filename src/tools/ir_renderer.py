"""Renderer abstraction for IR to image outputs.

This module supports the older SVG-as-IR `IRModel` and the new
`SemanticIR` (UML-first). When given a `SemanticIR` it will route
through the PlantUML adapter and return image bytes and the plantuml text.
"""
from __future__ import annotations

from typing import Dict, Tuple, Union

try:
    from src.ir.semantic_ir import SemanticIR
except Exception:
    SemanticIR = None

try:
    from src.tools.svg_ir import ir_to_svg, IRModel
except Exception:
    IRModel = None


def render_ir(ir: Union[IRModel, "SemanticIR"], renderer: str = "svg") -> Dict[str, str]:
    """Render IR to a result dict.

    - If `ir` is the older SVG `IRModel`, return {'renderer','svg'} as before.
    - If `ir` is a `SemanticIR`, use PlantUML adapter to produce image bytes
      and plantuml text and return {'renderer':'plantuml','plantuml':..., 'image_bytes': <base64>}
    """
    if SemanticIR is not None and isinstance(ir, SemanticIR):
        # avoid importing plantuml renderer heavy code at module import time
        from src.ir.plantuml_adapter import ir_to_plantuml
        from src.tools.plantuml_renderer import plantuml_to_image
        plant = ir_to_plantuml(ir, diagram_type=renderer if renderer else "context")
        img = plantuml_to_image(plant)
        # encode bytes as base64 string for transport in JSON-like dict
        import base64

        return {
            "renderer": "plantuml",
            "plantuml": plant,
            "image_base64": base64.b64encode(img).decode("ascii"),
        }

    if IRModel is not None and isinstance(ir, IRModel):
        svg_text = ir_to_svg(ir)
        return {"renderer": "svg", "svg": svg_text}

    raise ValueError("Unsupported IR type for rendering")