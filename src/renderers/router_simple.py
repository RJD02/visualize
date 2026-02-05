"""Simple renderer router used by PoC runner."""
from __future__ import annotations

from typing import Tuple


def choose_renderer(intent: str) -> Tuple[str, str]:
    if intent in ("story", "sequence"):
        return "mermaid", "story/sequence -> mermaid"
    if intent in ("system_context", "container", "component"):
        return "structurizr", "architecture intents -> structurizr"
    return "plantuml", "fallback -> plantuml"
