from src.ir_transforms import apply_feedback


def _sample_ir():
    return {
        "diagram": {
            "id": "d1",
            "type": "system_architecture",
            "blocks": [
                {
                    "id": "b1",
                    "type": "component",
                    "text": "Old",
                    "bbox": {"x": 0, "y": 0, "w": 100, "h": 40},
                    "style": {},
                    "annotations": {},
                }
            ],
            "relations": [],
        }
    }


def test_edit_text():
    ir = _sample_ir()
    fb = {"diagram_id": "d1", "block_id": "b1", "action": "edit_text", "payload": {"text": "New"}}
    new_ir, patches = apply_feedback(fb, ir)
    block = new_ir["diagram"]["blocks"][0]
    assert block["text"] == "New"
    assert patches[0]["op"] == "edit_text"


def test_reposition():
    ir = _sample_ir()
    fb = {"diagram_id": "d1", "block_id": "b1", "action": "reposition", "payload": {"bbox": {"x": 50}}}
    new_ir, _ = apply_feedback(fb, ir)
    block = new_ir["diagram"]["blocks"][0]
    assert block["bbox"]["x"] == 50
    assert block["bbox"]["w"] == 100


def test_add_block():
    ir = _sample_ir()
    fb = {"diagram_id": "d1", "action": "add_block", "payload": {"text": "Auth Service"}}
    new_ir, patches = apply_feedback(fb, ir)
    assert len(new_ir["diagram"]["blocks"]) == 2
    assert patches[0]["op"] == "add_block"


def test_invalid_block():
    ir = _sample_ir()
    fb = {"diagram_id": "d1", "block_id": "missing", "action": "edit_text", "payload": {"text": "X"}}
    try:
        apply_feedback(fb, ir)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "not found" in str(exc)
