from unittest.mock import Mock

import requests

from src.renderer import render_plantuml


def test_render_plantuml(monkeypatch, tmp_path):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.content = b"pngdata"
    mock_response.raise_for_status = Mock()

    def mock_get(*args, **kwargs):
        return mock_response

    monkeypatch.setattr(requests, "get", mock_get)
    from src.utils import config

    config.settings.output_dir = str(tmp_path)

    plantuml_text = "@startuml\n@enduml"
    path = render_plantuml(plantuml_text, "test")
    assert path.endswith("test.png")
