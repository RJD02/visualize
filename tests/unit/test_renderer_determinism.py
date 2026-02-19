import sys
import types


# Inject a lightweight fake `src.utils.config` before importing `src.renderer`
fake_cfg = types.ModuleType("src.utils.config")
fake_cfg.settings = types.SimpleNamespace(output_dir=".", plantuml_server_url="https://example.com/png/")
sys.modules["src.utils.config"] = fake_cfg

from src.renderer import _normalize_svg


def test_normalize_removes_comments_and_timestamps():
    svg = b"""
    <!-- generator: PlantUML 1.2 -->
    <svg id="_abc123" timestamp="2026-02-19T12:00:00Z">
      <g id="layer1">content</g>
    </svg>
    """

    normalized = _normalize_svg(svg)
    s = normalized.decode("utf-8")
    assert "generator" not in s
    assert "timestamp" not in s
    assert "_abc123" not in s
    assert "layer1" in s
