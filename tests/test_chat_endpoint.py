"""Tests for the unified /api/chat endpoint (specs_v42).

Tighter tests that mirror the ACTUAL shape of handle_message() return values,
including the new generated_images key populated from assistant_messages.

Verifies:
1.  Sending "generate diagram" returns diagram block with image_id in payload.
2.  Sending "analyze architecture" returns analysis block.
3.  Sending "animate this" returns animation block.
4.  Sending random text returns text block (no diagram block).
5.  Mixed response (text + diagram) returns multiple blocks in correct order.
6.  Envelope schema is always valid on every response type.
7.  session_id is auto-created when not supplied.
8.  Missing / empty message returns 400.
9.  Unknown session_id returns 404.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.server import app
from src.db_models import Session as SessionRecord


# ---------------------------------------------------------------------------
# Helpers — mirror EXACT shape returned by handle_message()
# ---------------------------------------------------------------------------

def _make_session(session_id=None):
    sid = session_id or uuid.uuid4()
    s = MagicMock(spec=SessionRecord)
    s.id = sid
    s.title = "test session"
    s.source_repo = None
    s.source_commit = None
    return s


def _make_image_entry(diagram_type="component", version=1):
    """One entry as returned in result['generated_images']."""
    return {
        "image_id": str(uuid.uuid4()),
        "image_version": version,
        "diagram_type": diagram_type,
        "ir_id": str(uuid.uuid4()),
    }


def _text_only_result(response="Here is your answer."):
    """handle_message() result with no generated images — plain text intent."""
    return {
        "intent": "explain",
        "response": response,
        "result": {},
        "plan": {},
        "plan_id": str(uuid.uuid4()),
        "tool_results": [],
        "generated_images": [],          # authoritative source — empty
    }


def _diagram_result(diagram_type="component", version=1):
    """handle_message() result with one generated image."""
    img = _make_image_entry(diagram_type, version)
    return {
        "intent": "diagram_change",
        "response": f"Generated {diagram_type} diagram(s).",
        "result": {},
        "plan": {},
        "plan_id": str(uuid.uuid4()),
        "tool_results": [
            # actual shape for LLM-rendered diagram
            {
                "tool": "llm.diagram",
                "rendering_service": "llm_plantuml",
                "output": {"image_id": img["image_id"], "audit_id": str(uuid.uuid4())},
                "audit_id": str(uuid.uuid4()),
                "execution_id": str(uuid.uuid4()),
            }
        ],
        "generated_images": [img],       # authoritative source
    }


def _multi_diagram_result():
    """Two diagrams (component + container) — tests ordering."""
    imgs = [_make_image_entry("component", 1), _make_image_entry("container", 2)]
    return {
        "intent": "diagram_change",
        "response": "Generated component, container diagram(s).",
        "result": {},
        "plan": {},
        "plan_id": str(uuid.uuid4()),
        "tool_results": [],
        "generated_images": imgs,
    }


def _analysis_result():
    """handle_message() result for analyze_architecture intent."""
    return {
        "intent": "analyze_architecture",
        "response": "Analysis complete.",
        "result": {
            "score": 72.5,
            "issues": ["Circular dependency detected"],
            "suggested_patches": ["Extract interface"],
        },
        "plan": {},
        "plan_id": str(uuid.uuid4()),
        "tool_results": [
            {
                "tool": "architecture_quality",
                "output": {
                    "score": 72.5,
                    "issues": ["Circular dependency detected"],
                    "suggested_patches": ["Extract interface"],
                },
            }
        ],
        "generated_images": [],
    }


def _animation_result():
    """handle_message() result for animate intent."""
    img = _make_image_entry("component", 1)
    return {
        "intent": "animate",
        "response": "Here is the animation.",
        "result": {},
        "plan": {},
        "plan_id": str(uuid.uuid4()),
        "tool_results": [],
        "generated_images": [img],
    }


def _mixed_result():
    """Text + diagram — both present."""
    img = _make_image_entry("container", 2)
    return {
        "intent": "diagram_change",
        "response": "Generated the container diagram with notes.",
        "result": {},
        "plan": {},
        "plan_id": str(uuid.uuid4()),
        "tool_results": [],
        "generated_images": [img],
    }


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Schema validator (shared assertion)
# ---------------------------------------------------------------------------

VALID_RESPONSE_TYPES = {"text", "diagram", "animation", "analysis", "mixed"}
VALID_BLOCK_TYPES = {"text", "diagram", "animation", "analysis", "action"}
REQUIRED_ENVELOPE_KEYS = {"response_type", "blocks", "state", "confidence", "session_id"}
REQUIRED_STATE_KEYS = {"ir_version", "has_diagram", "analysis_score"}


def assert_valid_envelope(data: dict):
    assert isinstance(data, dict), "Response body must be a dict"
    for k in REQUIRED_ENVELOPE_KEYS:
        assert k in data, f"Envelope missing required key: '{k}'"
    assert data["response_type"] in VALID_RESPONSE_TYPES, (
        f"response_type '{data['response_type']}' not in {VALID_RESPONSE_TYPES}"
    )
    assert isinstance(data["blocks"], list), "blocks must be a list"
    assert len(data["blocks"]) >= 1, "blocks must not be empty"
    for block in data["blocks"]:
        assert "block_type" in block, "Block missing block_type"
        assert "payload" in block, "Block missing payload"
        assert block["block_type"] in VALID_BLOCK_TYPES, (
            f"block_type '{block['block_type']}' not in {VALID_BLOCK_TYPES}"
        )
        assert isinstance(block["payload"], dict), "payload must be a dict"
    state = data["state"]
    for k in REQUIRED_STATE_KEYS:
        assert k in state, f"state missing key: '{k}'"
    assert isinstance(state["has_diagram"], bool), "state.has_diagram must be bool"
    assert isinstance(data["confidence"], (int, float)), "confidence must be numeric"
    assert isinstance(data["session_id"], str) and data["session_id"], "session_id must be non-empty string"


# ---------------------------------------------------------------------------
# Test 1 — generate diagram → diagram block with image_id
# ---------------------------------------------------------------------------

def test_generate_diagram_returns_diagram_block_with_image_id(client):
    session = _make_session()
    mock_result = _diagram_result("component", 1)
    expected_image_id = mock_result["generated_images"][0]["image_id"]

    with (
        patch("src.server.get_session", return_value=session),
        patch("src.server.handle_message", return_value=mock_result),
    ):
        resp = client.post("/api/chat", json={
            "message": "generate a component diagram",
            "session_id": str(session.id),
        })

    assert resp.status_code == 200
    data = resp.json()
    assert_valid_envelope(data)

    # Must contain a diagram block
    diagram_blocks = [b for b in data["blocks"] if b["block_type"] == "diagram"]
    assert len(diagram_blocks) >= 1, f"Expected ≥1 diagram block, got blocks: {[b['block_type'] for b in data['blocks']]}"

    # image_id must be present and correct
    first_diagram = diagram_blocks[0]
    assert "image_id" in first_diagram["payload"], "diagram block payload must have image_id"
    assert first_diagram["payload"]["image_id"] == expected_image_id

    # response_type and state
    assert data["response_type"] in ("diagram", "mixed")
    assert data["state"]["has_diagram"] is True
    assert data["state"]["ir_version"] == 1


# ---------------------------------------------------------------------------
# Test 2 — analyze architecture → analysis block
# ---------------------------------------------------------------------------

def test_analyze_architecture_returns_analysis_block(client):
    session = _make_session()

    with (
        patch("src.server.get_session", return_value=session),
        patch("src.server.handle_message", return_value=_analysis_result()),
    ):
        resp = client.post("/api/chat", json={
            "message": "analyze architecture",
            "session_id": str(session.id),
        })

    assert resp.status_code == 200
    data = resp.json()
    assert_valid_envelope(data)

    analysis_blocks = [b for b in data["blocks"] if b["block_type"] == "analysis"]
    assert len(analysis_blocks) >= 1, f"Expected analysis block, got: {[b['block_type'] for b in data['blocks']]}"

    payload = analysis_blocks[0]["payload"]
    assert "score" in payload, "analysis block must have score"
    assert "issues" in payload, "analysis block must have issues"
    assert "suggested_patches" in payload, "analysis block must have suggested_patches"
    assert payload["score"] == 72.5

    assert data["state"]["has_diagram"] is False


# ---------------------------------------------------------------------------
# Test 3 — animate this → animation block with image_id
# ---------------------------------------------------------------------------

def test_animate_returns_animation_block_with_image_id(client):
    session = _make_session()
    mock_result = _animation_result()
    expected_image_id = mock_result["generated_images"][0]["image_id"]

    with (
        patch("src.server.get_session", return_value=session),
        patch("src.server.handle_message", return_value=mock_result),
    ):
        resp = client.post("/api/chat", json={
            "message": "animate this",
            "session_id": str(session.id),
        })

    assert resp.status_code == 200
    data = resp.json()
    assert_valid_envelope(data)

    animation_blocks = [b for b in data["blocks"] if b["block_type"] == "animation"]
    assert len(animation_blocks) >= 1, f"Expected animation block, got: {[b['block_type'] for b in data['blocks']]}"
    assert animation_blocks[0]["payload"]["image_id"] == expected_image_id

    # No plain diagram blocks for pure animation
    diagram_blocks = [b for b in data["blocks"] if b["block_type"] == "diagram"]
    assert len(diagram_blocks) == 0, "Animation response must not contain diagram blocks"

    assert data["state"]["has_diagram"] is True


# ---------------------------------------------------------------------------
# Test 4 — random text → text block only, no diagram
# ---------------------------------------------------------------------------

def test_random_text_returns_text_block_only(client):
    session = _make_session()

    with (
        patch("src.server.get_session", return_value=session),
        patch("src.server.handle_message", return_value=_text_only_result("Microservices are small services.")),
    ):
        resp = client.post("/api/chat", json={
            "message": "what is a microservice?",
            "session_id": str(session.id),
        })

    assert resp.status_code == 200
    data = resp.json()
    assert_valid_envelope(data)

    block_types = [b["block_type"] for b in data["blocks"]]
    assert "text" in block_types, f"Expected text block, got: {block_types}"
    assert "diagram" not in block_types, "Text-only response must not contain diagram blocks"
    assert "animation" not in block_types, "Text-only response must not contain animation blocks"

    text_block = next(b for b in data["blocks"] if b["block_type"] == "text")
    assert "Microservices" in text_block["payload"]["markdown"]

    assert data["response_type"] == "text"
    assert data["state"]["has_diagram"] is False
    assert data["state"]["ir_version"] is None


# ---------------------------------------------------------------------------
# Test 5 — mixed: text + diagram → correct block order
# ---------------------------------------------------------------------------

def test_mixed_response_has_text_before_diagram(client):
    session = _make_session()
    mock_result = _mixed_result()
    expected_image_id = mock_result["generated_images"][0]["image_id"]

    with (
        patch("src.server.get_session", return_value=session),
        patch("src.server.handle_message", return_value=mock_result),
    ):
        resp = client.post("/api/chat", json={
            "message": "generate a container diagram and explain it",
            "session_id": str(session.id),
        })

    assert resp.status_code == 200
    data = resp.json()
    assert_valid_envelope(data)

    block_types = [b["block_type"] for b in data["blocks"]]
    assert "text" in block_types, f"Expected text block, got: {block_types}"
    assert "diagram" in block_types, f"Expected diagram block, got: {block_types}"
    assert len(data["blocks"]) >= 2

    # text must come before diagram
    assert block_types.index("text") < block_types.index("diagram"), (
        f"text block must precede diagram block; got order: {block_types}"
    )

    # image_id correct
    diagram_block = next(b for b in data["blocks"] if b["block_type"] == "diagram")
    assert diagram_block["payload"]["image_id"] == expected_image_id

    assert data["response_type"] == "mixed"
    assert data["state"]["has_diagram"] is True


# ---------------------------------------------------------------------------
# Test 6 — envelope schema valid for every response type
# ---------------------------------------------------------------------------

def test_envelope_schema_valid_for_all_response_types(client):
    session = _make_session()
    cases = [
        _text_only_result(),
        _diagram_result(),
        _analysis_result(),
        _animation_result(),
        _mixed_result(),
    ]
    for mock_result in cases:
        with (
            patch("src.server.get_session", return_value=session),
            patch("src.server.handle_message", return_value=mock_result),
        ):
            resp = client.post("/api/chat", json={
                "message": "test",
                "session_id": str(session.id),
            })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code} for intent={mock_result['intent']}"
        assert_valid_envelope(resp.json())


# ---------------------------------------------------------------------------
# Test 7 — session auto-created when not supplied
# ---------------------------------------------------------------------------

def test_session_auto_created_when_not_supplied(client):
    new_session = _make_session()

    with (
        patch("src.server.create_session", return_value=new_session),
        patch("src.server.handle_message", return_value=_text_only_result("Hello!")),
    ):
        resp = client.post("/api/chat", json={"message": "hello"})

    assert resp.status_code == 200
    data = resp.json()
    assert_valid_envelope(data)
    assert data["session_id"] == str(new_session.id), (
        f"Expected session_id={new_session.id}, got {data['session_id']}"
    )


# ---------------------------------------------------------------------------
# Test 8 — empty message returns 400
# ---------------------------------------------------------------------------

def test_empty_message_returns_400(client):
    session = _make_session()
    with patch("src.server.get_session", return_value=session):
        resp = client.post("/api/chat", json={
            "message": "",
            "session_id": str(session.id),
        })
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body, f"Expected error key in body, got: {body}"


# ---------------------------------------------------------------------------
# Test 9 — unknown session_id returns 404
# ---------------------------------------------------------------------------

def test_unknown_session_id_returns_404(client):
    with patch("src.server.get_session", return_value=None):
        resp = client.post("/api/chat", json={
            "message": "hello",
            "session_id": str(uuid.uuid4()),
        })
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body, f"Expected error key in body, got: {body}"
