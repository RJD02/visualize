"""Simple intent detection heuristics for diagram generation.

Rules implemented (POC):
- GitHub URL provided -> system_context
- Short arrow-based text ("->" or "→") -> container or sequence
- Mostly prose (multiple sentences) -> story
- Documents or long text -> generic_summary
"""
from __future__ import annotations

from typing import Optional


def detect_intent(text: Optional[str] = None, github_url: Optional[str] = None, has_files: bool = False) -> str:
    """Return one of: system_context, container, component, sequence, story, generic_summary

    Heuristics are intentionally conservative and deterministic for POC.
    """
    if github_url:
        return "system_context"

    if not text:
        # No textual input; fall back to generic summary
        return "generic_summary"

    txt = text.strip()
    lower = txt.lower()

    # If text contains obvious architecture arrows -> prefer container/sequence
    if "->" in txt or "→" in txt or "--" in txt:
        # If it looks like steps (numbered or newline-separated short lines), choose sequence
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        short_lines = sum(1 for l in lines if len(l.split()) < 8)
        if len(lines) >= 2 and short_lines >= max(1, len(lines)//2):
            return "sequence"
        return "container"

    # If multiple sentences and reasonably short words, treat as story / narrative
    sentences = [s for s in txt.split('.') if s.strip()]
    word_count = len(txt.split())
    if len(sentences) >= 2 and word_count > 10:
        return "story"

    # If contains words commonly found in architectures, pick system_context
    arch_words = {"service", "api", "database", "db", "queue", "cache", "auth", "frontend", "backend"}
    if any(w in lower for w in arch_words):
        return "system_context"

    # Documents or many lines -> generic summary
    if len(txt) > 800 or '\n' in txt and len(txt.splitlines()) > 6:
        return "generic_summary"

    # Default fallback
    return "system_context"
