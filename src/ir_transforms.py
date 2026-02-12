"""Deterministic IR mutation engine for feedback edits."""
from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, List, Tuple


def _find_block(diagram: Dict[str, Any], block_id: str) -> Dict[str, Any] | None:
    for block in diagram.get("blocks", []) or []:
        if block.get("id") == block_id:
            return block
    return None


def _ensure_blocks(diagram: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks = diagram.get("blocks")
    if blocks is None:
        blocks = []
        diagram["blocks"] = blocks
    return blocks


def _ensure_relations(diagram: Dict[str, Any]) -> List[Dict[str, Any]]:
    rels = diagram.get("relations")
    if rels is None:
        rels = []
        diagram["relations"] = rels
    return rels


def _new_block_id(existing: List[Dict[str, Any]]) -> str:
    existing_ids = {b.get("id") for b in existing}
    while True:
        candidate = f"block-{uuid.uuid4().hex[:8]}"
        if candidate not in existing_ids:
            return candidate


def apply_feedback(feedback: Dict[str, Any], ir_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Apply feedback to IR and return (new_ir, patches)."""
    new_payload = copy.deepcopy(ir_payload)
    diagram = new_payload.get("diagram") or new_payload.get("ir", {}).get("diagram")
    if not diagram:
        raise ValueError("IR missing diagram")

    action = (feedback.get("action") or "").strip()
    if not action:
        raise ValueError("Feedback action is required")

    block_id = feedback.get("block_id")
    payload = feedback.get("payload") or {}

    patches: List[Dict[str, Any]] = []

    if action == "edit_text":
        if not block_id:
            raise ValueError("block_id required for edit_text")
        block = _find_block(diagram, block_id)
        if not block:
            raise ValueError(f"block_id '{block_id}' not found")
        before = block.get("text")
        block["text"] = str(payload.get("text") or "")
        patches.append({"op": "edit_text", "block_id": block_id, "before": before, "after": block["text"]})
    elif action == "reposition":
        if not block_id:
            raise ValueError("block_id required for reposition")
        block = _find_block(diagram, block_id)
        if not block:
            raise ValueError(f"block_id '{block_id}' not found")
        bbox_update = payload.get("bbox") or {}
        bbox = block.get("bbox") or {}
        bbox.update({k: v for k, v in bbox_update.items() if v is not None})
        block["bbox"] = bbox
        patches.append({"op": "reposition", "block_id": block_id, "bbox": bbox_update})
    elif action == "style":
        if not block_id:
            raise ValueError("block_id required for style")
        block = _find_block(diagram, block_id)
        if not block:
            raise ValueError(f"block_id '{block_id}' not found")
        style_update = payload.get("style") or {}
        style = block.get("style") or {}
        style.update(style_update)
        block["style"] = style
        patches.append({"op": "style", "block_id": block_id, "style": style_update})
    elif action == "annotate":
        if not block_id:
            raise ValueError("block_id required for annotate")
        block = _find_block(diagram, block_id)
        if not block:
            raise ValueError(f"block_id '{block_id}' not found")
        annotations = block.get("annotations") or {}
        annotations.update(payload.get("annotations") or {})
        block["annotations"] = annotations
        patches.append({"op": "annotate", "block_id": block_id, "annotations": payload.get("annotations") or {}})
    elif action == "hide":
        if not block_id:
            raise ValueError("block_id required for hide")
        block = _find_block(diagram, block_id)
        if not block:
            raise ValueError(f"block_id '{block_id}' not found")
        block["hidden"] = True
        patches.append({"op": "hide", "block_id": block_id})
    elif action == "show":
        if not block_id:
            raise ValueError("block_id required for show")
        block = _find_block(diagram, block_id)
        if not block:
            raise ValueError(f"block_id '{block_id}' not found")
        block["hidden"] = False
        patches.append({"op": "show", "block_id": block_id})
    elif action == "add_block":
        blocks = _ensure_blocks(diagram)
        new_id = payload.get("id") or _new_block_id(blocks)
        new_block = {
            "id": new_id,
            "type": payload.get("type") or "component",
            "text": payload.get("text") or "New Block",
            "bbox": payload.get("bbox") or {"x": 0, "y": 0, "w": 120, "h": 40},
            "style": payload.get("style") or {},
            "annotations": payload.get("annotations") or {},
            "version": int(payload.get("version") or 1),
        }
        blocks.append(new_block)
        patches.append({"op": "add_block", "block_id": new_id})
    elif action == "remove_block":
        if not block_id:
            raise ValueError("block_id required for remove_block")
        blocks = _ensure_blocks(diagram)
        before_count = len(blocks)
        blocks[:] = [b for b in blocks if b.get("id") != block_id]
        _ensure_relations(diagram)
        diagram["relations"] = [r for r in diagram.get("relations", []) if r.get("from") != block_id and r.get("to") != block_id]
        if len(blocks) == before_count:
            raise ValueError(f"block_id '{block_id}' not found")
        patches.append({"op": "remove_block", "block_id": block_id})
    else:
        raise ValueError(f"Unsupported feedback action '{action}'")

    return new_payload, patches
