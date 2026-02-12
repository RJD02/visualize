"""Validation helpers for LLM-supplied UML diagrams."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List


_PLANTUML_BLOCK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"!\s*include", re.IGNORECASE), "!include"),
    (re.compile(r"!\s*import", re.IGNORECASE), "!import"),
    (re.compile(r"!\s*pragma", re.IGNORECASE), "!pragma"),
    (re.compile(r"!\s*function", re.IGNORECASE), "!function"),
    (re.compile(r"!\s*procedure", re.IGNORECASE), "!procedure"),
    (re.compile(r"!\s*define", re.IGNORECASE), "!define"),
    (re.compile(r"!\s*undef", re.IGNORECASE), "!undef"),
    (re.compile(r"skinparam\s+backgroundimage", re.IGNORECASE), "skinparam backgroundImage"),
    (re.compile(r"skinparam\s+stylesheet", re.IGNORECASE), "skinparam stylesheet"),
    (re.compile(r"url\s*\(", re.IGNORECASE), "url(...)"),
    (re.compile(r"file:\/\/", re.IGNORECASE), "file URI"),
)

_ALLOWED_SKINPARAM_KEYS = {
    "componentStyle",
    "roundcorner",
    "shadowing",
    "defaultFontName",
    "defaultFontSize",
    "wrapWidth",
    "maxMessageSize",
}
_ALLOWED_SKINPARAM_KEYS_LOWER = {key.lower() for key in _ALLOWED_SKINPARAM_KEYS}

_MERMAID_BLOCK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"<\s*script", re.IGNORECASE), "<script>"),
    (re.compile(r"<\s*iframe", re.IGNORECASE), "<iframe>"),
    (re.compile(r"<\s*img", re.IGNORECASE), "<img>"),
    (re.compile(r"javascript:\s*", re.IGNORECASE), "javascript URI"),
)


@dataclass
class DiagramValidationResult:
    format: str
    sanitized_text: str
    warnings: List[str]
    blocked_tokens: List[str]


class DiagramValidationError(ValueError):
    """Raised when a diagram contains blocked tokens."""

    def __init__(self, message: str, result: DiagramValidationResult):
        super().__init__(message)
        self.result = result


def _normalize_format(diagram_format: str | None) -> str:
    token = (diagram_format or "").strip().lower()
    if token in {"plantuml", "plant", "puml"}:
        return "plantuml"
    if token in {"mermaid", "mmd"}:
        return "mermaid"
    raise ValueError("Unknown diagram format: %s" % diagram_format)


def _ensure_bounds(text: str, start_marker: str, end_marker: str, warnings: List[str]) -> str:
    lowered = text.lower()
    if start_marker.lower() not in lowered:
        warnings.append(f"Added {start_marker}")
        text = f"{start_marker}\n{text}"
    if end_marker.lower() not in lowered:
        warnings.append(f"Added {end_marker}")
        text = f"{text}\n{end_marker}"
    return text


def _scan_patterns(text: str, patterns: Iterable[tuple[re.Pattern[str], str]]) -> List[str]:
    blocked: List[str] = []
    for pattern, label in patterns:
        if pattern.search(text):
            blocked.append(label)
    return blocked


def _validate_skinparams(text: str) -> List[str]:
    blocked: List[str] = []
    for match in re.finditer(r"skinparam\s+([a-z0-9_]+)", text, re.IGNORECASE):
        key = match.group(1)
        if key.lower() not in _ALLOWED_SKINPARAM_KEYS_LOWER:
            blocked.append(f"skinparam {key}")
    return blocked


def _sanitize_mermaid(text: str) -> str:
    text = text.replace("\r", "")
    return text.strip()


def _sanitize_plantuml(text: str, warnings: List[str]) -> str:
    text = text.replace("\r", "")
    stripped = text.strip()
    stripped = _ensure_bounds(stripped, "@startuml", "@enduml", warnings)
    return stripped


def validate_and_sanitize(diagram_text: str, diagram_format: str) -> DiagramValidationResult:
    """Validate an LLM-provided diagram and normalize its contents."""
    fmt = _normalize_format(diagram_format)
    warnings: List[str] = []
    blocked: List[str] = []
    payload = (diagram_text or "").strip()

    if not payload:
        result = DiagramValidationResult(fmt, "", warnings, blocked)
        raise DiagramValidationError("Diagram text is empty", result)

    if fmt == "plantuml":
        sanitized = _sanitize_plantuml(payload, warnings)
        blocked.extend(_scan_patterns(sanitized, _PLANTUML_BLOCK_PATTERNS))
        blocked.extend(_validate_skinparams(sanitized))
    else:
        sanitized = _sanitize_mermaid(payload)
        blocked.extend(_scan_patterns(sanitized, _MERMAID_BLOCK_PATTERNS))

    result = DiagramValidationResult(fmt, sanitized, warnings, blocked)
    if blocked:
        raise DiagramValidationError("Diagram contains blocked directives", result)
    return result
