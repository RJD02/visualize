"""Diagram intent detection for diverse inputs."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Optional


@dataclass(frozen=True)
class IntentResult:
    primary: str
    intents: List[str]
    reason: str


_ARCH_KEYWORDS = {
    "api", "service", "database", "db", "gateway", "client", "server", "system",
    "container", "component", "queue", "cache", "worker", "auth", "login",
}

_STORY_CUES = {
    "rain", "lamp", "shadow", "umbrella", "he", "she", "they", "him", "her",
    "suddenly", "silence", "whisper", "night", "train", "station",
}

_SEQUENCE_CUES = {"->", "then", "after", "before", "step", "sequence", "flow"}


def detect_intent(text: str | None, github_url: Optional[str] = None, has_files: bool = False) -> IntentResult:
    lowered = (text or "").lower()

    if github_url:
        return IntentResult(
            primary="system_context",
            intents=["system_context", "container", "component"],
            reason="github_url",
        )

    if any(tok in lowered for tok in _SEQUENCE_CUES):
        return IntentResult(primary="sequence", intents=["sequence"], reason="sequence cues")

    arch_hits = sum(1 for tok in _ARCH_KEYWORDS if tok in lowered)
    story_hits = sum(1 for tok in _STORY_CUES if tok in lowered)
    sentence_count = len([s for s in re.split(r"[.!?]+", text or "") if s.strip()])

    if story_hits >= 1 and sentence_count >= 2:
        return IntentResult(primary="story", intents=["story"], reason="narrative cues")

    if arch_hits >= 2:
        return IntentResult(primary="container", intents=["container"], reason="architecture cues")

    if has_files:
        return IntentResult(primary="generic_summary", intents=["generic_summary"], reason="document input")

    return IntentResult(primary="generic_summary", intents=["generic_summary"], reason="fallback")
