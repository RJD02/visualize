"""REST API server."""
from __future__ import annotations

import base64
import mimetypes
from typing import Generator, List, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from sqlalchemy.orm import Session as DbSession
from sqlalchemy import select, text

from src.db import Base, SessionLocal, engine
from src.schemas import (
    ArchitecturePlanResponse,
    DiagramFileResponse,
    ImageIRResponse,
    ImageResponse,
    MCPDiscoverResponse,
    MCPExecuteRequest,
    MCPExecuteResponse,
    MessageResponse,
    PlanSummaryResponse,
    PlanHistoryResponse,
    PlanExecutionResponse,
    SessionCreateResponse,
    SessionDetailResponse,
    StylingAuditResponse,
)
from src.db_models import DiagramIR, Image, Session as SessionRecord, StylingAudit
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_mcp_tools
from src import mcp_tool as mcp_tool_adapter
from src.services.session_service import (
    create_session,
    get_latest_plan,
    get_plan_with_history,
    get_session,
    handle_message,
    ingest_input,
    list_diagrams,
    list_images,
    list_messages,
    list_plan_records,
    save_edited_ir,
)
from src.feedback_controller import process_feedback, list_ir_history, get_ir as get_ir_v2, create_demo_diagram
from src.services.styling_audit_service import get_styling_audit, list_styling_audits, list_audits_by_plan
from src.animation_resolver import inject_animation, validate_presentation_spec
from src.animation.diagram_renderer import render_svg
from src.intent.semantic_aesthetic_ir import SemanticAestheticIR
from src.utils.file_utils import read_text_file
import src.animation.svg_parser as svg_parser_module
import src.animation.animation_plan_generator as plan_module
import src.animation.css_injector as css_module
import src.animation.diagram_renderer as renderer_module
import json

app = FastAPI(title="Architecture Visualization API")

ui_dir = Path(__file__).resolve().parent.parent / "ui" / "dist"
if ui_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")
    assets_dir = ui_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

outputs_dir = Path(__file__).resolve().parent.parent / "outputs"
if outputs_dir.exists():
    app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")


@app.get("/")
async def index():
    if ui_dir.exists():
        return FileResponse(ui_dir / "index.html")
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}


def get_db() -> Generator[DbSession, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _serialize_styling_audit(audit: StylingAudit) -> StylingAuditResponse:
    return StylingAuditResponse(
        id=audit.id,
        session_id=audit.session_id,
        plan_id=audit.plan_id,
        diagram_id=audit.diagram_id,
        diagram_type=audit.diagram_type,
        mode=audit.mode,
        timestamp=audit.timestamp,
        user_prompt=audit.user_prompt,
        llm_format=audit.llm_format,
        llm_diagram=audit.llm_diagram,
        sanitized_diagram=audit.sanitized_diagram,
        extracted_intent=audit.extracted_intent,
        styling_plan=audit.styling_plan,
        execution_steps=list(audit.execution_steps or []),
        agent_reasoning=audit.agent_reasoning,
        renderer_input_before=audit.renderer_input_before,
        renderer_input_after=audit.renderer_input_after,
        svg_before=audit.svg_before,
        svg_after=audit.svg_after,
        validation_warnings=list(audit.validation_warnings or []),
        blocked_tokens=list(audit.blocked_tokens or []),
    )


def _serialize_plan_execution(execution) -> PlanExecutionResponse:
    return PlanExecutionResponse(
        id=execution.id,
        step_index=execution.step_index,
        tool_name=execution.tool_name,
        arguments=execution.arguments,
        output=execution.output,
        audit_id=execution.audit_id,
        duration_ms=execution.duration_ms,
        created_at=execution.created_at,
    )


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_message_columns()
    register_mcp_tools(mcp_registry)


def _ensure_message_columns() -> None:
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(messages)"))
            existing = {row[1] for row in rows}
            if "message_type" not in existing:
                conn.execute(text("ALTER TABLE messages ADD COLUMN message_type VARCHAR(16) DEFAULT 'text'"))
            if "image_version" not in existing:
                conn.execute(text("ALTER TABLE messages ADD COLUMN image_version INTEGER"))
            if "diagram_type" not in existing:
                conn.execute(text("ALTER TABLE messages ADD COLUMN diagram_type VARCHAR(64)"))
            if "ir_id" not in existing:
                conn.execute(text("ALTER TABLE messages ADD COLUMN ir_id UUID"))
            rows = conn.execute(text("PRAGMA table_info(images)"))
            existing_images = {row[1] for row in rows}
            if "ir_id" not in existing_images:
                conn.execute(text("ALTER TABLE images ADD COLUMN ir_id UUID"))
            rows = conn.execute(text("PRAGMA table_info(styling_audits)"))
            existing_audits = {row[1] for row in rows}
            if "plan_id" not in existing_audits:
                conn.execute(text("ALTER TABLE styling_audits ADD COLUMN plan_id UUID"))
            if "llm_format" not in existing_audits:
                conn.execute(text("ALTER TABLE styling_audits ADD COLUMN llm_format VARCHAR(16)"))
            if "llm_diagram" not in existing_audits:
                conn.execute(text("ALTER TABLE styling_audits ADD COLUMN llm_diagram TEXT"))
            if "sanitized_diagram" not in existing_audits:
                conn.execute(text("ALTER TABLE styling_audits ADD COLUMN sanitized_diagram TEXT"))
            if "validation_warnings" not in existing_audits:
                conn.execute(text("ALTER TABLE styling_audits ADD COLUMN validation_warnings JSON"))
            if "blocked_tokens" not in existing_audits:
                conn.execute(text("ALTER TABLE styling_audits ADD COLUMN blocked_tokens JSON"))
    else:
        statements = [
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS message_type VARCHAR(16) DEFAULT 'text'",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS image_version INTEGER",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS diagram_type VARCHAR(64)",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS ir_id UUID",
            "ALTER TABLE images ADD COLUMN IF NOT EXISTS ir_id UUID",
            "ALTER TABLE styling_audits ADD COLUMN IF NOT EXISTS plan_id UUID",
            "ALTER TABLE styling_audits ADD COLUMN IF NOT EXISTS llm_format VARCHAR(16)",
            "ALTER TABLE styling_audits ADD COLUMN IF NOT EXISTS llm_diagram TEXT",
            "ALTER TABLE styling_audits ADD COLUMN IF NOT EXISTS sanitized_diagram TEXT",
            "ALTER TABLE styling_audits ADD COLUMN IF NOT EXISTS validation_warnings JSON",
            "ALTER TABLE styling_audits ADD COLUMN IF NOT EXISTS blocked_tokens JSON",
        ]
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))


@app.post("/api/sessions", response_model=SessionCreateResponse)
def create_session_api(db: DbSession = Depends(get_db)):
    session = create_session(db)
    return SessionCreateResponse(session_id=session.id, title=session.title)


@app.post("/api/sessions/{session_id}/ingest")
async def ingest_api(
    session_id: str,
    files: Optional[List[UploadFile]] = File(None),
    text: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None),
    db: DbSession = Depends(get_db),
):
    session = get_session(db, session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    if not files and not text and not github_url:
        return JSONResponse(status_code=400, content={"error": "Provide files or text"})
    temp_paths = None
    if files:
        temp_paths = []
        for uf in files:
            content = await uf.read()
            path = f"/tmp/{uf.filename}"
            with open(path, "wb") as f:
                f.write(content)
            temp_paths.append(path)
    try:
        # When ingest is triggered via the API (file upload / GitHub URL), do not
        # auto-create assistant images or messages. Images are created only when
        # the user explicitly requests generation via chat to avoid preloading UI.
        result = ingest_input(db, session, temp_paths, text, github_url=github_url, generate_images=False)
        return result
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/sessions/{session_id}/messages")
def message_api(session_id: str, payload: dict, db: DbSession = Depends(get_db)):
    session = get_session(db, session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    content = payload.get("content", "")
    if not content:
        return JSONResponse(status_code=400, content={"error": "Missing content"})
    try:
        return handle_message(db, session, content)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/sessions/{session_id}", response_model=SessionDetailResponse)
def session_detail(session_id: str, db: DbSession = Depends(get_db)):
    session = get_session(db, session_id)
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
    plan = get_latest_plan(db, session.id)
    plan_records = list_plan_records(db, session.id)
    # Only show preloaded diagrams after the user has sent a message.
    # This prevents auto-generated PlantUML diagrams from appearing when a
    # session is first created by the system/agents.
    recent_messages = list_messages(db, session.id)
    show_diagrams = any(m.role == "user" for m in recent_messages)

    image_records = list_images(db, session.id) if show_diagrams else []
    ir_map: dict[str, DiagramIR] = {}
    if image_records:
        ir_ids = list({img.ir_id for img in image_records if getattr(img, "ir_id", None)})
        if ir_ids:
            ir_rows = db.execute(select(DiagramIR).where(DiagramIR.id.in_(ir_ids))).scalars()
            ir_map = {ir.id: ir for ir in ir_rows}

    images_payload: list[ImageResponse] = []
    for img in image_records:
        ir_record = ir_map.get(img.ir_id)
        images_payload.append(
            ImageResponse(
                id=img.id,
                version=img.version,
                file_path=img.file_path,
                prompt=img.prompt,
                reason=img.reason,
                created_at=img.created_at,
                diagram_type=ir_record.diagram_type if ir_record else None,
                ir_id=getattr(img, "ir_id", None),
                ir_svg_text=ir_record.svg_text if ir_record else None,
                ir_metadata=ir_record.ir_json if ir_record else None,
            )
        )

    return SessionDetailResponse(
        session_id=session.id,
        title=session.title,
        source_repo=session.source_repo,
        source_commit=session.source_commit,
        architecture_plan=ArchitecturePlanResponse(data=plan.data, created_at=plan.created_at) if plan else None,
        images=images_payload,
        diagrams=[
            DiagramFileResponse(
                diagram_type=d.diagram_type,
                file_path=d.file_path,
                created_at=d.created_at,
            )
            for d in (list_diagrams(db, session.id) if show_diagrams else [])
        ],
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                intent=m.intent,
                image_id=m.image_id,
                message_type=getattr(m, "message_type", None),
                image_version=getattr(m, "image_version", None),
                diagram_type=getattr(m, "diagram_type", None),
                created_at=m.created_at,
            )
            for m in list_messages(db, session.id)
        ],
        plans=[
            PlanSummaryResponse(
                id=p.id,
                session_id=p.session_id,
                intent=p.intent,
                plan_json=p.plan_json,
                metadata=p.metadata_json,
                executed=p.executed,
                created_at=p.created_at,
            )
            for p in plan_records
        ],
    )


@app.get("/api/plans/{plan_id}", response_model=PlanHistoryResponse)
def plan_history(plan_id: str, db: DbSession = Depends(get_db)):
    plan, executions = get_plan_with_history(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    audits = list_audits_by_plan(db, plan.id)
    return PlanHistoryResponse(
        id=plan.id,
        session_id=plan.session_id,
        intent=plan.intent,
        plan_json=plan.plan_json,
        metadata=plan.metadata_json,
        executed=plan.executed,
        created_at=plan.created_at,
        executions=[_serialize_plan_execution(e) for e in executions],
        audits=[_serialize_styling_audit(a) for a in audits],
    )


@app.get("/api/images/{image_id}/ir", response_model=ImageIRResponse)
def image_ir_detail(image_id: str, db: DbSession = Depends(get_db)):
    image = db.get(Image, image_id)
    if not image:
        return JSONResponse(status_code=404, content={"error": "Image not found"})
    if not getattr(image, "ir_id", None):
        return JSONResponse(status_code=404, content={"error": "IR not available"})
    ir = db.get(DiagramIR, image.ir_id)
    if not ir:
        return JSONResponse(status_code=404, content={"error": "IR not found"})
    return ImageIRResponse(image_id=image.id, diagram_type=ir.diagram_type, svg_text=ir.svg_text)


@app.post("/edit")
async def edit(
    edit_prompt: str = Form(...),
    output_name: str = Form("diagram"),
):
    return {"error": "Deprecated. Use /api/sessions/{id}/messages."}


@app.post("/api/images/{image_id}/ir")
def save_image_ir(image_id: str, payload: dict, db: DbSession = Depends(get_db)):
    svg_text = payload.get("svg_text") if payload else None
    reason = payload.get("reason") if payload else None
    if svg_text is None or not str(svg_text).strip():
        return JSONResponse(status_code=400, content={"error": "Missing svg_text"})
    image = db.get(Image, image_id)
    if not image:
        return JSONResponse(status_code=404, content={"error": "Image not found"})
    try:
        created_image = save_edited_ir(db, image_id, svg_text, reason or "edited via ui")
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return ImageResponse(
        id=created_image.id,
        version=created_image.version,
        file_path=created_image.file_path,
        prompt=created_image.prompt,
        reason=created_image.reason,
        created_at=created_image.created_at,
    )


@app.post("/api/feedback")
def feedback_endpoint(payload: dict, db: DbSession = Depends(get_db)):
    try:
        result = process_feedback(db, payload or {})
    except Exception as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return JSONResponse(content=result)


@app.get("/api/ir/{diagram_id}")
def get_ir_endpoint(diagram_id: str, db: DbSession = Depends(get_db)):
    try:
        payload = get_ir_v2(db, diagram_id)
    except Exception as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    return JSONResponse(content=payload)


@app.get("/api/ir/{diagram_id}/history")
def get_ir_history_endpoint(diagram_id: str, db: DbSession = Depends(get_db)):
    try:
        payload = list_ir_history(db, diagram_id)
    except Exception as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    return JSONResponse(content={"history": payload})


@app.get("/api/demo/diagram")
def demo_diagram_endpoint(db: DbSession = Depends(get_db)):
    result = create_demo_diagram(db)
    return JSONResponse(content=result)


@app.get("/api/diagrams/{diagram_id}/styling/audit", response_model=List[StylingAuditResponse])
def list_styling_audits_api(diagram_id: str, db: DbSession = Depends(get_db)):
    try:
        diagram_uuid = UUID(str(diagram_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid diagram id")
    audits = list_styling_audits(db, diagram_uuid)
    return [_serialize_styling_audit(a) for a in audits]


@app.get("/api/diagrams/{diagram_id}/styling/audit/{audit_id}", response_model=StylingAuditResponse)
def get_styling_audit_api(diagram_id: str, audit_id: str, db: DbSession = Depends(get_db)):
    try:
        diagram_uuid = UUID(str(diagram_id))
        audit_uuid = UUID(str(audit_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid identifier")
    audit = get_styling_audit(db, audit_uuid, diagram_uuid)
    if not audit:
        raise HTTPException(status_code=404, detail="Styling audit not found")
    return _serialize_styling_audit(audit)


@app.post('/api/diagram/render')
def render_diagram_api(payload: dict, db: DbSession = Depends(get_db)):
    """Render diagram SVG in static or animated mode.

    payload: { mode: 'static'|'animated', image_id?: str, file_path?: str, presentationSpec?: {...} }
    """
    mode = (payload or {}).get('mode', 'static')
    image_id = (payload or {}).get('image_id')
    file_path = (payload or {}).get('file_path')
    spec = (payload or {}).get('presentationSpec')
    enhanced = bool((payload or {}).get('enhanced', False))

    svg_text = None
    # prefer IR if available
    if image_id:
        img = db.get(Image, image_id)
        if not img:
            raise HTTPException(status_code=404, detail='Image not found')
        # attempt to find latest IR for this image
        if getattr(img, 'ir_id', None):
            ir = db.get(DiagramIR, img.ir_id)
            if ir:
                svg_text = ir.svg_text
        # fallback to file_path
        if not svg_text:
            file_path = img.file_path

    if (svg_text is None or not str(svg_text).strip()) and file_path:
        # read file
        try:
            root = Path(file_path)
            if not root.exists():
                raise HTTPException(status_code=404, detail='SVG file not found')
            try:
                svg_text = read_text_file(str(root))
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    if svg_text is None or not str(svg_text).strip():
        raise HTTPException(status_code=400, detail='No svg source provided')

    semantic_intent = None
    if image_id:
        img = db.get(Image, image_id)
        if img and getattr(img, "ir_id", None):
            ir = db.get(DiagramIR, img.ir_id)
            if ir and isinstance(ir.ir_json, dict):
                intent_payload = ir.ir_json.get("aesthetic_intent")
                if isinstance(intent_payload, dict):
                    semantic_intent = SemanticAestheticIR.from_dict(intent_payload)

    if mode == 'static':
        if enhanced:
            svg_text = render_svg(svg_text, animated=False, enhanced=True, semantic_intent=semantic_intent)
        return JSONResponse(content={'svg': svg_text})

    # animated mode
    if not spec:
        raise HTTPException(status_code=400, detail='presentationSpec required for animated mode')

    valid, errors = validate_presentation_spec(svg_text, spec)
    if not valid:
        raise HTTPException(status_code=400, detail={'errors': errors})

    try:
        if enhanced:
            svg_text = render_svg(svg_text, animated=False, enhanced=True, semantic_intent=semantic_intent)
        animated = inject_animation(svg_text, spec)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return JSONResponse(content={'svg': animated})


@app.get('/api/diagram/render')
def render_diagram_svg(
    format: str = Query(default="svg"),
    animated: bool = Query(default=False),
    debug: bool = Query(default=False),
    enhanced: bool = Query(default=False),
    image_id: Optional[str] = Query(default=None),
    file_path: Optional[str] = Query(default=None),
    db: DbSession = Depends(get_db),
):
    """Render static or animated SVG using inferred animation plan.

    Query params:
      format=svg
      animated=true|false
      image_id or file_path
    """
    if format != "svg":
        raise HTTPException(status_code=400, detail="Only svg format is supported")

    svg_text = None
    resolved_path = None
    img_record: Image | None = None
    ir_record: DiagramIR | None = None

    if image_id:
        img_record = db.get(Image, image_id)
        if not img_record:
            raise HTTPException(status_code=404, detail="Image not found")
        resolved_path = img_record.file_path
        if getattr(img_record, "ir_id", None):
            ir_candidate = db.get(DiagramIR, img_record.ir_id)
            if ir_candidate:
                ir_record = ir_candidate
                svg_text = ir_candidate.svg_text

    if file_path:
        resolved_path = file_path

    if (svg_text is None or not str(svg_text).strip()) and resolved_path:
        path = Path(resolved_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="SVG file not found")
        if path.suffix.lower() == ".svg":
            try:
                svg_text = read_text_file(str(path))
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))
        else:
            try:
                blob = path.read_bytes()
            except Exception as exc:
                raise HTTPException(status_code=500, detail=str(exc))
            mime, _ = mimetypes.guess_type(path.name)
            if not mime:
                mime = "image/png" if path.suffix.lower() == ".png" else "application/octet-stream"
            encoded = base64.b64encode(blob).decode("ascii")
            svg_text = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%">'
                f'<image href="data:{mime};base64,{encoded}" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" />'
                '</svg>'
            )

    if svg_text is None or not str(svg_text).strip():
        raise HTTPException(status_code=400, detail="No svg source provided")

    semantic_intent = None
    intent_source = ir_record
    if intent_source is None and img_record and getattr(img_record, "ir_id", None):
        intent_source = db.get(DiagramIR, img_record.ir_id)
    if intent_source and isinstance(intent_source.ir_json, dict):
        intent_payload = intent_source.ir_json.get("aesthetic_intent")
        if isinstance(intent_payload, dict):
            semantic_intent = SemanticAestheticIR.from_dict(intent_payload)

    if animated:
        svg_text = render_svg(svg_text, animated=True, debug=debug, enhanced=enhanced, semantic_intent=semantic_intent, use_v2=enhanced)
    elif enhanced:
        svg_text = render_svg(svg_text, animated=False, debug=debug, enhanced=True, semantic_intent=semantic_intent)

    return JSONResponse(content={"svg": svg_text})


@app.get("/mcp/discover", response_model=MCPDiscoverResponse)
def mcp_discover_endpoint():
    tools = mcp_registry.list_tools()
    return MCPDiscoverResponse(tools=tools)


@app.post("/mcp/execute", response_model=MCPExecuteResponse)
def mcp_execute_endpoint(payload: MCPExecuteRequest, db: DbSession = Depends(get_db)):
    context: dict = {"db": db}
    if payload.session_id:
        session_record = db.get(SessionRecord, payload.session_id)
        if not session_record:
            raise HTTPException(status_code=404, detail="Session not found")
        context["session"] = session_record
        context["session_id"] = str(session_record.id)
    if payload.plan_id:
        context["plan_id"] = str(payload.plan_id)
    user_prompt = payload.args.get("userPrompt") if isinstance(payload.args, dict) else None
    if user_prompt:
        context.setdefault("user_message", user_prompt)
    try:
        result = mcp_registry.execute(payload.tool_id, payload.args or {}, context=context)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    audit_id = result.get("audit_id") or result.get("auditId")
    return MCPExecuteResponse(result=result, audit_id=audit_id)


@app.post("/mcp/tool/generate")
def mcp_tool_generate(payload: dict, db: DbSession = Depends(get_db)):
    result = mcp_tool_adapter.generate(payload or {}, db=db)
    return JSONResponse(content=result)


@app.post("/mcp/tool/feedback")
def mcp_tool_feedback(payload: dict, db: DbSession = Depends(get_db)):
    result = mcp_tool_adapter.apply_feedback(payload or {}, db=db)
    return JSONResponse(content=result)


@app.get("/mcp/tool/ir/{diagram_id}")
def mcp_tool_get_ir(diagram_id: str, db: DbSession = Depends(get_db)):
    result = mcp_tool_adapter.get_ir_payload(diagram_id, db=db)
    return JSONResponse(content=result)


@app.get("/mcp/tool/ir/{diagram_id}/history")
def mcp_tool_get_ir_history(diagram_id: str, db: DbSession = Depends(get_db)):
    result = mcp_tool_adapter.get_ir_history_payload(diagram_id, db=db)
    return JSONResponse(content=result)


@app.get("/mcp/tool/export/svg/{diagram_id}")
def mcp_tool_export_svg(diagram_id: str, db: DbSession = Depends(get_db)):
    result = mcp_tool_adapter.export_svg(diagram_id, db=db)
    return JSONResponse(content=result)


@app.get("/mcp/tool/export/gif/{diagram_id}")
def mcp_tool_export_gif(diagram_id: str, db: DbSession = Depends(get_db)):
    result = mcp_tool_adapter.export_gif(diagram_id, db=db)
    return JSONResponse(content=result)


@app.get("/api/debug/modules")
def debug_modules():
    return {
        "svg_parser": svg_parser_module.__file__,
        "plan_generator": plan_module.__file__,
        "css_injector": css_module.__file__,
        "diagram_renderer": renderer_module.__file__,
    }
