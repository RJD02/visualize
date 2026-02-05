"""Render PlantUML text to an image using a PlantUML server."""
from __future__ import annotations

from pathlib import Path

import requests

from src.utils.config import settings
from src.utils.file_utils import ensure_dir
from src.utils.plantuml_encode import plantuml_encode


_MAX_GET_URL_LEN = 2000


def _post_plantuml(url: str, plantuml_text: str) -> requests.Response:
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    return requests.post(url, data=plantuml_text.encode("utf-8"), headers=headers, timeout=30)


def _raise_for_status(response: requests.Response, context: str) -> None:
    if response.status_code >= 400:
        snippet = (response.text or "").strip()
        if len(snippet) > 300:
            snippet = snippet[:300] + "..."
        raise requests.HTTPError(f"{context} failed ({response.status_code}): {snippet}")


def sanitize_plantuml(plantuml_text: str) -> str:
    """Best-effort cleanup for malformed PlantUML braces and markers."""
    lines = plantuml_text.splitlines()
    cleaned = []
    balance = 0
    for line in lines:
        new_line = []
        for ch in line:
            if ch == "{":
                balance += 1
                new_line.append(ch)
            elif ch == "}":
                if balance == 0:
                    continue
                balance -= 1
                new_line.append(ch)
            else:
                new_line.append(ch)
        cleaned.append("".join(new_line))

    if not any(l.strip().startswith("@startuml") for l in cleaned):
        cleaned.insert(0, "@startuml")
    if not any(l.strip().startswith("@enduml") for l in cleaned):
        cleaned.append("@enduml")

    if balance > 0:
        end_index = next((i for i, l in enumerate(cleaned) if l.strip().startswith("@enduml")), len(cleaned))
        for _ in range(balance):
            cleaned.insert(end_index, "}")
            end_index += 1

    return "\n".join(cleaned)


def _svg_url(base_url: str) -> str:
    if base_url.endswith("/png/"):
        return base_url.replace("/png/", "/svg/")
    if base_url.endswith("/png"):
        return base_url[:-4] + "/svg"
    if base_url.endswith("/"):
        return base_url + "svg/"
    return base_url + "/svg/"


def render_plantuml_png(plantuml_text: str, output_name: str) -> str:
    """Render PlantUML text and save the PNG locally."""
    output_dir = ensure_dir(settings.output_dir)
    cleaned = sanitize_plantuml(plantuml_text)
    encoded = plantuml_encode(cleaned)
    url = f"{settings.plantuml_server_url}{encoded}"
    if len(url) > _MAX_GET_URL_LEN:
        response = _post_plantuml(settings.plantuml_server_url, cleaned)
        _raise_for_status(response, "PlantUML POST")
    else:
        response = requests.get(url, timeout=30)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            if response.status_code == 400:
                response = _post_plantuml(settings.plantuml_server_url, cleaned)
                _raise_for_status(response, "PlantUML POST")
            else:
                raise
    output_path = Path(output_dir) / f"{output_name}.png"
    output_path.write_bytes(response.content)
    return str(output_path)


def render_plantuml_svg(plantuml_text: str, output_name: str) -> str:
    """Render PlantUML text and save the SVG locally."""
    output_dir = ensure_dir(settings.output_dir)
    cleaned = sanitize_plantuml(plantuml_text)
    encoded = plantuml_encode(cleaned)
    url = f"{_svg_url(settings.plantuml_server_url)}{encoded}"
    svg_base = _svg_url(settings.plantuml_server_url)
    if len(url) > _MAX_GET_URL_LEN:
        response = _post_plantuml(svg_base, cleaned)
        _raise_for_status(response, "PlantUML POST")
    else:
        response = requests.get(url, timeout=30)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            if response.status_code == 400:
                response = _post_plantuml(svg_base, cleaned)
                _raise_for_status(response, "PlantUML POST")
            else:
                raise
    output_path = Path(output_dir) / f"{output_name}.svg"
    output_path.write_bytes(response.content)
    return str(output_path)


def render_plantuml(plantuml_text: str, output_name: str) -> str:
    """Backward-compatible PNG rendering."""
    return render_plantuml_png(plantuml_text, output_name)
