from pathlib import Path

from src.aesthetics.aesthetic_intelligence import generate_aesthetic_plan_llm
from src.aesthetics.style_transformer import apply_aesthetic_plan
from src.utils.file_utils import read_text_file


def test_apply_aesthetic_plan_injects_style():
    svg_path = next(Path("outputs").glob("*.svg"), None)
    if svg_path is None:
        return
    try:
        svg_text = read_text_file(str(svg_path))
    except Exception:
        svg_text = svg_path.read_text(encoding="utf-8", errors="ignore")
    plan = generate_aesthetic_plan_llm(svg_text, "svg-test", animation_present=False)
    enhanced = apply_aesthetic_plan(svg_text, plan)
    assert "ai-aesthetic-style" in enhanced
    assert "ai-node" in enhanced or "ai-edge" in enhanced
