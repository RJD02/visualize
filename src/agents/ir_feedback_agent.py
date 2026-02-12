"""Rule-based IR feedback interpreter agent."""
from __future__ import annotations

from typing import Any, Dict


def interpret_feedback(feedback_text: str, ir: Dict[str, Any]) -> Dict[str, Any]:
    """Return a structured mutation plan from free-form feedback.

    This is a deterministic placeholder; production uses explicit feedback payloads.
    """
    lowered = (feedback_text or "").lower()
    if "rename" in lowered and "to" in lowered:
        return {"operation": "update_node_label", "confidence": 0.3}
    if "remove" in lowered or "delete" in lowered:
        return {"operation": "delete_node", "confidence": 0.3}
    if "move" in lowered and "zone" in lowered:
        return {"operation": "move_zone", "confidence": 0.3}
    return {"operation": "unknown", "confidence": 0.1}
