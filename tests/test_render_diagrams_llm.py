from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from src.tools import plantuml_renderer as pr


def test_render_diagrams_records_audit_for_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(pr.settings, "output_dir", str(tmp_path))

    def fake_render_plantuml_svg(diagram_text: str, output_name: str) -> str:
        svg_path = Path(tmp_path) / f"{output_name}.svg"
        svg_path.write_text("<svg />", encoding="utf-8")
        return str(svg_path)

    recorded: dict[str, dict] = {}

    def fake_record_styling_audit(db, **kwargs):  # noqa: ANN001 - test stub
        recorded["kwargs"] = kwargs

        class _Audit:
            def __init__(self):
                self.id = uuid4()

        return _Audit()

    monkeypatch.setattr(pr, "render_plantuml_svg", fake_render_plantuml_svg)
    monkeypatch.setattr(pr, "record_styling_audit", fake_record_styling_audit)

    diagrams = [
        {
            "type": "component",
            "llm_diagram": "@startuml\nAlice -> Bob\n@enduml",
            "format": "plantuml",
        }
    ]
    files = pr.render_diagrams(
        diagrams,
        "llm_default",
        audit_context={
            "db": object(),
            "session_id": uuid4(),
            "plan_id": uuid4(),
            "user_prompt": "describe component",
        },
    )

    assert Path(files[0]).exists()
    assert recorded["kwargs"]["plan_id"] is not None
    assert recorded["kwargs"]["llm_format"] == "plantuml"


def test_render_diagrams_handles_mermaid_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(pr.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(pr, "render_mermaid_svg", lambda text: "<svg>mermaid</svg>")

    diagrams = [
        {
            "type": "system_context",
            "llm_diagram": "graph LR; A-->B;",
            "format": "mermaid",
        }
    ]
    files = pr.render_diagrams(diagrams, "merm")
    svg_path = Path(files[0])
    assert svg_path.read_text(encoding="utf-8") == "<svg>mermaid</svg>"
    assert svg_path.with_suffix(".mmd").read_text(encoding="utf-8").startswith("graph LR")
