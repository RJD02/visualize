from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base
from src.services import session_service
from src.services.session_service import _apply_patch_ops_to_ir
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_mcp_tools, tool_styling_transform_agent as real_transform
from src.mcp.tools import apply_ir_node_styles_to_svg
from src.services import styling_audit_service


def _plan():
    return {
        "system_name": "Spec Test System",
        "diagram_views": ["system_context", "container"],
        "zones": {
            "clients": ["Client"],
            "edge": ["Gateway"],
            "core_services": ["Service"],
            "external_services": ["External"],
            "data_stores": ["DB"],
        },
        "relationships": [
            {"from": "Client", "to": "Gateway", "type": "sync", "description": "call"}
        ],
        "visual_hints": {"layout": "top-down", "group_by_zone": True},
    }


class FakeWorkflow:
    def run(self, files, text, output_name):
        return {"architecture_plan": _plan(), "images": [], "visual": {}, "plantuml": {"files": []}, "evaluation": {"score": 1, "warnings": []}}

    def run_edit(self, edit_text, output_name):
        return {"visual": {}, "images": []}


class PlannerEditIR:
    def plan(self, message, state, tools):
        return {
            "intent": "edit_image",
            "diagram_count": None,
            "diagrams": [],
            "target_image_id": state.get("active_image_id"),
            "target_diagram_type": "system_context",
            "instructions": message,
            "requires_regeneration": False,
            "plan": [{"tool": "edit_diagram_ir", "arguments": {"instruction": message}}],
        }


def _create_session(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(session_service, "ADKWorkflow", FakeWorkflow)
    monkeypatch.setattr(session_service, "ConversationPlannerAgent", PlannerEditIR)

    register_mcp_tools(mcp_registry)
    db = SessionLocal()
    session = session_service.create_session(db)
    session_service.ingest_input(db, session, files=None, text="hello")
    return db, session


def test_edit_smoke_creates_new_ir(monkeypatch):
    db, session = _create_session(monkeypatch)

    before = session_service.list_ir_versions(db, session.id)
    assert len(before) >= 1

    # return a safe patch that updates zone_order
    def fake_transform(context, ir, user_edit_suggestion=None, mode="style_only", constraints=None):
        return {"patch_ops": [{"op": "replace", "path": "/zone_order", "value": ["clients", "core_services", "edge"]}]}

    monkeypatch.setattr("src.mcp.tools.tool_styling_transform_agent", fake_transform)

    session_service.handle_message(db, session, "reorder zones")

    after = session_service.list_ir_versions(db, session.id)
    assert len(after) == len(before) + 1
    latest = after[-1]
    # zone_order lives inside enriched_ir when the wrapper structure is present
    enriched = latest.ir_json.get("enriched_ir") or {}
    zone = enriched.get("zone_order") or latest.ir_json.get("zone_order")
    assert zone == ["clients", "core_services", "edge"]


def test_patch_validation_rejects_invalid_path(monkeypatch):
    db, session = _create_session(monkeypatch)
    before = session_service.list_ir_versions(db, session.id)

    def fake_transform_invalid(context, ir, user_edit_suggestion=None, mode="style_only", constraints=None):
        return {"patch_ops": [{"op": "replace", "path": "/nodes/nonexistent/shape", "value": "circle"}]}

    monkeypatch.setattr("src.mcp.tools.tool_styling_transform_agent", fake_transform_invalid)

    session_service.handle_message(db, session, "make missing circular")

    after = session_service.list_ir_versions(db, session.id)
    # should not create a new IR version due to invalid patch
    assert len(after) == len(before)

    # an audit should have been recorded for the failed patch application
    # query audits by session to find the patch_apply_failed entry
    from sqlalchemy import select
    from src.db_models import StylingAudit

    audits = list(db.execute(select(StylingAudit).where(StylingAudit.session_id == session.id)).scalars())
    assert any(("patch_apply_failed" in a.execution_steps) or a.agent_reasoning for a in audits)


def test_structural_integrity_detection(monkeypatch):
    db, session = _create_session(monkeypatch)
    before = session_service.list_ir_versions(db, session.id)
    parent = before[-1]

    # attempt to rename a node id so edges become orphaned
    # use the existing node id 'node_service' which should exist for label 'Service'
    def fake_transform_rename(context, ir, user_edit_suggestion=None, mode="style_only", constraints=None):
        return {"patch_ops": [{"op": "replace", "path": "/nodes/node_service/node_id", "value": "node_service_renamed"}]}

    monkeypatch.setattr("src.mcp.tools.tool_styling_transform_agent", fake_transform_rename)

    session_service.handle_message(db, session, "rename service id")

    after = session_service.list_ir_versions(db, session.id)
    # should not create a new IR due to orphan edge detection
    assert len(after) == len(before)


def test_no_recursion_indicator(monkeypatch):
    db, session = _create_session(monkeypatch)
    before = session_service.list_ir_versions(db, session.id)

    # transform returns an updated_ir that contains an attempted tool call hint; Main Agent should treat it as data
    def fake_transform_toolhint(context, ir, user_edit_suggestion=None, mode="style_only", constraints=None):
        updated = dict(ir or {})
        updated.setdefault("meta", {})["attempted_tool_call"] = {"tool": "edit_diagram_ir"}
        return {"updated_ir": updated}

    monkeypatch.setattr("src.mcp.tools.tool_styling_transform_agent", fake_transform_toolhint)

    session_service.handle_message(db, session, "do an internal tool call")

    after = session_service.list_ir_versions(db, session.id)
    assert len(after) == len(before) + 1
    latest = after[-1]
    # the meta field should be present in the ir_json but should not have triggered any extra tool executions
    assert latest.ir_json.get("meta", {}).get("attempted_tool_call", {}).get("tool") == "edit_diagram_ir"


def test_version_history_parent_linked(monkeypatch):
    db, session = _create_session(monkeypatch)
    before = session_service.list_ir_versions(db, session.id)
    parent = before[-1]

    def fake_transform(context, ir, user_edit_suggestion=None, mode="style_only", constraints=None):
        return {"patch_ops": [{"op": "replace", "path": "/globalIntent/title", "value": "Renamed"}]}

    monkeypatch.setattr("src.mcp.tools.tool_styling_transform_agent", fake_transform)

    session_service.handle_message(db, session, "rename title")

    after = session_service.list_ir_versions(db, session.id)
    assert len(after) == len(before) + 1
    latest = after[-1]
    assert str(latest.parent_ir_id) == str(parent.id)


# ── Tests for enriched_ir wrapper navigation ──────────────────────────────────


def _wrapped_ir():
    """Return a realistic IR with nodes/edges nested inside enriched_ir."""
    return {
        "intent": "component",
        "enriched_ir": {
            "diagram_type": "component",
            "layout": "left-right",
            "zone_order": ["backend", "data"],
            "nodes": [
                {"node_id": "middleware", "label": "middleware", "role": "service", "shape": "rounded", "zone": "backend", "node_style": {"fillColor": "#FDE68A"}},
                {"node_id": "controllers", "label": "controllers", "role": "service", "shape": "rounded", "zone": "backend", "node_style": {"fillColor": "#E0E7FF"}},
                {"node_id": "db", "label": "database", "role": "data_store", "shape": "cylinder", "zone": "data", "node_style": {"fillColor": "#FBCFE8"}},
            ],
            "edges": [
                {"edge_id": "e1", "from": "controllers", "to": "middleware", "label": "calls"},
                {"edge_id": "e2", "from": "middleware", "to": "db", "label": "queries"},
            ],
        },
        "aesthetic_intent": {"theme": "minimal"},
    }


def test_styling_agent_finds_nodes_in_enriched_ir():
    """tool_styling_transform_agent correctly finds nodes nested inside enriched_ir."""
    ir = _wrapped_ir()
    result = real_transform(
        context={},
        ir=ir,
        user_edit_suggestion="make the middleware block circular",
    )
    # Should produce patch_ops (NOT error/unhandled_suggestion)
    assert "patch_ops" in result, f"Expected patch_ops, got: {result}"
    ops = result["patch_ops"]
    # At least one op should target the middleware node shape
    shape_ops = [op for op in ops if "middleware" in op.get("path", "") and "shape" in op.get("path", "")]
    assert len(shape_ops) >= 1, f"Expected shape patch for middleware, got ops: {ops}"
    assert shape_ops[0]["value"] == "circle"


def test_styling_agent_color_change_enriched_ir():
    """Color change works when nodes are inside enriched_ir."""
    ir = _wrapped_ir()
    result = real_transform(
        context={},
        ir=ir,
        user_edit_suggestion="change the database color to red",
    )
    assert "patch_ops" in result, f"Expected patch_ops, got: {result}"
    ops = result["patch_ops"]
    color_ops = [op for op in ops if "db" in op.get("path", "") and "fillColor" in op.get("path", "")]
    assert len(color_ops) >= 1, f"Expected color patch for db, got ops: {ops}"


def test_styling_agent_hide_node_enriched_ir():
    """Hide operation works when nodes are inside enriched_ir."""
    ir = _wrapped_ir()
    result = real_transform(
        context={},
        ir=ir,
        user_edit_suggestion="hide the controllers component",
    )
    assert "patch_ops" in result, f"Expected patch_ops, got: {result}"
    ops = result["patch_ops"]
    hide_ops = [op for op in ops if "controllers" in op.get("path", "")]
    assert len(hide_ops) >= 1, f"Expected hide patch for controllers, got ops: {ops}"


def test_apply_patch_ops_enriched_ir_nodes():
    """_apply_patch_ops_to_ir correctly patches nodes nested inside enriched_ir."""
    ir = _wrapped_ir()
    patch_ops = [
        {"op": "replace", "path": "/nodes/middleware/shape", "value": "circle"},
    ]
    result = _apply_patch_ops_to_ir(ir, patch_ops)
    # The middleware node inside enriched_ir should now have shape=circle
    nodes = result["enriched_ir"]["nodes"]
    middleware = next(n for n in nodes if n["node_id"] == "middleware")
    assert middleware["shape"] == "circle"


def test_apply_patch_ops_enriched_ir_node_style():
    """_apply_patch_ops_to_ir correctly patches node_style inside enriched_ir."""
    ir = _wrapped_ir()
    patch_ops = [
        {"op": "replace", "path": "/nodes/db/node_style/fillColor", "value": "#FF0000"},
    ]
    result = _apply_patch_ops_to_ir(ir, patch_ops)
    nodes = result["enriched_ir"]["nodes"]
    db_node = next(n for n in nodes if n["node_id"] == "db")
    assert db_node["node_style"]["fillColor"] == "#FF0000"


def test_apply_patch_ops_enriched_ir_zone_order():
    """_apply_patch_ops_to_ir writes zone_order into enriched_ir when wrapper is present."""
    ir = _wrapped_ir()
    patch_ops = [
        {"op": "replace", "path": "/zone_order", "value": ["data", "backend"]},
    ]
    result = _apply_patch_ops_to_ir(ir, patch_ops)
    assert result["enriched_ir"]["zone_order"] == ["data", "backend"]


def test_apply_ir_node_styles_to_svg_enriched_ir():
    """apply_ir_node_styles_to_svg finds nodes inside enriched_ir."""
    ir = _wrapped_ir()
    # Minimal SVG with a data-block-id matching a node
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<g data-block-id="middleware">'
        '<rect class="node-rect" fill="#FDE68A"/>'
        '<text class="node-text">middleware</text>'
        '</g></svg>'
    )
    result = apply_ir_node_styles_to_svg(svg, ir)
    # The fill attribute should be applied from node_style
    assert 'fill="#FDE68A"' in result or "FDE68A" in result


def test_shape_change_rect_to_circle_in_svg():
    """Shape change from rect to circle is reflected in SVG output."""
    ir = {
        "enriched_ir": {
            "nodes": [
                {"node_id": "middleware", "label": "middleware", "shape": "circle", "node_style": {"fillColor": "#FDE68A"}},
            ],
            "edges": [],
        },
    }
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<g data-block-id="middleware">'
        '<rect class="node-rect" x="100" y="50" width="140" height="48" fill="none" stroke="#64748b"/>'
        '<text class="node-text" x="108" y="78">middleware</text>'
        '</g></svg>'
    )
    result = apply_ir_node_styles_to_svg(svg, ir)
    # rect should be replaced with circle
    assert "circle" in result, f"Expected circle element in SVG, got: {result}"
    # Original rect should no longer be in the middleware group
    # (there may be rects in other parts of SVG, so just check after the block-id)
    after_block = result.split("middleware")[1] if "middleware" in result else result
    assert "circle" in after_block


def test_shape_change_rect_to_diamond_in_svg():
    """Shape change from rect to diamond produces polygon in SVG."""
    ir = {
        "enriched_ir": {
            "nodes": [
                {"node_id": "svc", "label": "service", "shape": "diamond", "node_style": {}},
            ],
            "edges": [],
        },
    }
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<g data-block-id="svc">'
        '<rect class="node-rect" x="100" y="50" width="140" height="48" fill="none" stroke="#64748b"/>'
        '<text class="node-text" x="108" y="78">service</text>'
        '</g></svg>'
    )
    result = apply_ir_node_styles_to_svg(svg, ir)
    assert "polygon" in result, f"Expected polygon for diamond shape, got: {result}"
    assert "points" in result


def test_shape_change_preserves_fill_color():
    """Shape change preserves the existing fill color and also applies node_style."""
    ir = {
        "enriched_ir": {
            "nodes": [
                {"node_id": "mw", "label": "mw", "shape": "circle", "node_style": {"fillColor": "#FF0000"}},
            ],
            "edges": [],
        },
    }
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<g data-block-id="mw">'
        '<rect class="node-rect" x="10" y="10" width="100" height="50" fill="#AABBCC" stroke="#000"/>'
        '<text class="node-text" x="18" y="38">mw</text>'
        '</g></svg>'
    )
    result = apply_ir_node_styles_to_svg(svg, ir)
    assert "circle" in result
    # node_style fillColor should be applied (overrides original fill)
    assert "FF0000" in result


def test_end_to_end_shape_patch_and_svg():
    """Full chain: styling agent generates patch, patch is applied, SVG is updated."""
    ir = _wrapped_ir()  # middleware has shape='rounded'
    # 1. Styling agent generates patch_ops
    result = real_transform(
        context={},
        ir=ir,
        user_edit_suggestion="make the middleware block circular",
    )
    assert "patch_ops" in result

    # 2. Apply patch_ops to IR
    patched_ir = _apply_patch_ops_to_ir(ir, result["patch_ops"])
    middleware = next(n for n in patched_ir["enriched_ir"]["nodes"] if n["node_id"] == "middleware")
    assert middleware["shape"] == "circle"

    # 3. Apply to SVG
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<g data-block-id="middleware">'
        '<rect class="node-rect" x="100" y="50" width="140" height="48" fill="none" stroke="#64748b"/>'
        '<text class="node-text" x="108" y="78">middleware</text>'
        '</g></svg>'
    )
    final_svg = apply_ir_node_styles_to_svg(svg, patched_ir)
    assert "circle" in final_svg, f"Expected circle in final SVG, got: {final_svg}"


def test_apply_patch_ops_flat_ir_still_works():
    """Flat IR (nodes at top level, no enriched_ir) still works correctly."""
    flat_ir = {
        "nodes": [
            {"node_id": "svc", "label": "Service", "shape": "rect", "node_style": {}},
        ],
        "edges": [],
        "zone_order": ["core"],
    }
    patch_ops = [
        {"op": "replace", "path": "/nodes/svc/shape", "value": "circle"},
    ]
    result = _apply_patch_ops_to_ir(flat_ir, patch_ops)
    svc = next(n for n in result["nodes"] if n["node_id"] == "svc")
    assert svc["shape"] == "circle"
