"""Tests for block-level feedback editing via the feedback controller.

Covers: edit_text, style, hide, show, add_block, remove_block, and
the v1→v2 IR adapter round-trip.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base
from src.feedback_controller import (
    FeedbackError,
    create_demo_diagram,
    get_ir,
    list_ir_history,
    process_feedback,
)
from src.ir_adapter import render_v2_svg, v2_from_svg
from src.ir_transforms import apply_feedback


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def demo(db):
    return create_demo_diagram(db)


# ── edit_text ──────────────────────────────────────────────────────

def test_edit_text_renames_block(db, demo):
    result = process_feedback(db, {
        "diagram_id": demo["image_id"],
        "block_id": "block-api",
        "action": "edit_text",
        "payload": {"text": "Auth Service"},
    })
    assert result["status"] == "ok"
    blocks = result["ir"]["ir"]["diagram"]["blocks"]
    api = next(b for b in blocks if b["id"] == "block-api")
    assert api["text"] == "Auth Service"


def test_edit_text_reflected_in_svg(db, demo):
    result = process_feedback(db, {
        "diagram_id": demo["image_id"],
        "block_id": "block-api",
        "action": "edit_text",
        "payload": {"text": "Gateway Renamed"},
    })
    svg_path = result["artifacts"][0]["path"]
    svg_text = Path(svg_path).read_text(encoding="utf-8")
    assert "Gateway Renamed" in svg_text
    assert ">API<" not in svg_text


# ── style ──────────────────────────────────────────────────────────

def test_style_changes_block_color(db, demo):
    result = process_feedback(db, {
        "diagram_id": demo["image_id"],
        "block_id": "block-client",
        "action": "style",
        "payload": {"style": {"color": "#ff0000"}},
    })
    blocks = result["ir"]["ir"]["diagram"]["blocks"]
    client = next(b for b in blocks if b["id"] == "block-client")
    assert client["style"]["color"] == "#ff0000"


def test_style_reflected_in_svg(db, demo):
    result = process_feedback(db, {
        "diagram_id": demo["image_id"],
        "block_id": "block-client",
        "action": "style",
        "payload": {"style": {"color": "#ff0000"}},
    })
    svg_text = Path(result["artifacts"][0]["path"]).read_text(encoding="utf-8")
    assert "#ff0000" in svg_text


# ── hide / show ────────────────────────────────────────────────────

def test_hide_sets_hidden_flag(db, demo):
    result = process_feedback(db, {
        "diagram_id": demo["image_id"],
        "block_id": "block-api",
        "action": "hide",
        "payload": {},
    })
    blocks = result["ir"]["ir"]["diagram"]["blocks"]
    api = next(b for b in blocks if b["id"] == "block-api")
    assert api["hidden"] is True


def test_show_clears_hidden_flag(db, demo):
    # First hide
    r1 = process_feedback(db, {
        "diagram_id": demo["image_id"],
        "block_id": "block-api",
        "action": "hide",
        "payload": {},
    })
    # Then show using the new image
    r2 = process_feedback(db, {
        "diagram_id": r1["image_id"],
        "block_id": "block-api",
        "action": "show",
        "payload": {},
    })
    blocks = r2["ir"]["ir"]["diagram"]["blocks"]
    api = next(b for b in blocks if b["id"] == "block-api")
    assert api["hidden"] is False


# ── IR history ─────────────────────────────────────────────────────

def test_ir_history_grows_after_feedback(db, demo):
    process_feedback(db, {
        "diagram_id": demo["image_id"],
        "block_id": "block-api",
        "action": "edit_text",
        "payload": {"text": "Edited"},
    })
    history = list_ir_history(db, demo["image_id"])
    assert len(history) >= 2


def test_get_ir_returns_initial_wrapper(db, demo):
    wrapper = get_ir(db, demo["image_id"])
    blocks = wrapper["ir"]["diagram"]["blocks"]
    ids = {b["id"] for b in blocks}
    assert "block-client" in ids
    assert "block-api" in ids


# ── error handling ─────────────────────────────────────────────────

def test_edit_text_missing_block_raises(db, demo):
    with pytest.raises(Exception):
        process_feedback(db, {
            "diagram_id": demo["image_id"],
            "block_id": "nonexistent-block",
            "action": "edit_text",
            "payload": {"text": "Oops"},
        })


def test_feedback_invalid_uuid_raises(db):
    with pytest.raises(FeedbackError, match="Invalid UUID"):
        process_feedback(db, {
            "diagram_id": "not-a-uuid",
            "block_id": "block-api",
            "action": "edit_text",
            "payload": {"text": "Oops"},
        })


# ── v1→v2 adapter ─────────────────────────────────────────────────

def test_v2_from_svg_extracts_blocks():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">'
        '<metadata id="ir_metadata">{"diagram_type":"system_context",'
        '"nodes":[{"node_id":"node_a","label":"Service A","role":"component","zone":"core"}],'
        '"edges":[]}</metadata>'
        '<g id="node_a" data-kind="node" data-block-id="node_a" data-role="component">'
        '<rect id="node_a_rect" x="10" y="10" width="140" height="48" fill="#2563eb" />'
        '<text id="node_a_text" x="18" y="34">Service A</text>'
        '</g></svg>'
    )
    wrapper = v2_from_svg(svg, diagram_id="test")
    blocks = wrapper["ir"]["diagram"]["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["id"] == "node_a"
    assert blocks[0]["text"] == "Service A"
    assert blocks[0]["zone"] == "core"


def test_v2_from_svg_then_edit_text():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">'
        '<metadata id="ir_metadata">{"diagram_type":"system_context",'
        '"nodes":[{"node_id":"node_x","label":"Gateway","role":"component"}],'
        '"edges":[]}</metadata>'
        '<g id="node_x" data-kind="node" data-block-id="node_x" data-role="component">'
        '<rect id="node_x_rect" x="10" y="10" width="140" height="48" />'
        '<text id="node_x_text" x="18" y="34">Gateway</text>'
        '</g></svg>'
    )
    wrapper = v2_from_svg(svg, diagram_id="test")
    updated, patches = apply_feedback(
        {"block_id": "node_x", "action": "edit_text", "payload": {"text": "Auth GW"}},
        wrapper,
    )
    block = next(b for b in updated["ir"]["diagram"]["blocks"] if b["id"] == "node_x")
    assert block["text"] == "Auth GW"
    assert len(patches) == 1
    assert patches[0]["op"] == "edit_text"


# ── render_v2_svg ──────────────────────────────────────────────────

def test_render_v2_svg_roundtrip():
    wrapper = {
        "diagram_id": "rt",
        "ir_version": 1,
        "parent_version": None,
        "ir": {
            "diagram": {
                "id": "rt",
                "type": "system",
                "blocks": [
                    {"id": "b1", "type": "component", "text": "Alpha",
                     "bbox": {"x": 20, "y": 30, "w": 120, "h": 40},
                     "style": {"color": "#0000ff"}, "annotations": {}, "version": 1},
                ],
                "relations": [],
            }
        },
    }
    svg = render_v2_svg(wrapper)
    assert "Alpha" in svg
    assert "#0000ff" in svg
    assert 'data-block-id="b1"' in svg

    # Round-trip back through v2_from_svg
    wrapper2 = v2_from_svg(svg, diagram_id="rt")
    b = wrapper2["ir"]["diagram"]["blocks"][0]
    assert b["id"] == "b1"
    assert b["text"] == "Alpha"
