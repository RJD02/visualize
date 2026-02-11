"""REST API server."""
from __future__ import annotations

from typing import Generator, List, Optional

from fastapi import Depends, FastAPI, File, Form, UploadFile, Query
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from sqlalchemy.orm import Session as DbSession
from sqlalchemy import text

from src.db import Base, SessionLocal, engine
from src.schemas import (
    ArchitecturePlanResponse,
    DiagramFileResponse,
    ImageResponse,
    ImageIRResponse,
    MessageResponse,
    SessionCreateResponse,
    SessionDetailResponse,
)
from src.db_models import DiagramIR, Image
from src.mcp.registry import mcp_registry
from src.mcp.tools import register_mcp_tools
from src.services.session_service import (
    create_session,
    get_latest_plan,
    get_session,
    handle_message,
    ingest_input,
    list_diagrams,
    list_images,
    list_messages,
    save_edited_ir,
)
from src.animation_resolver import inject_animation, validate_presentation_spec
from src.animation.diagram_renderer import render_svg
from src.intent.semantic_aesthetic_ir import SemanticAestheticIR
from src.utils.file_utils import read_text_file
import src.animation.svg_parser as svg_parser_module
import src.animation.animation_plan_generator as plan_module
import src.animation.css_injector as css_module
import src.animation.diagram_renderer as renderer_module
from src.db_models import DiagramIR, Image
from fastapi import HTTPException
import json

app = FastAPI(title="Architecture Visualization API")

ui_dir = Path(__file__).resolve().parent.parent / "ui" / "dist"
if ui_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

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
        result = ingest_input(db, session, temp_paths, text, github_url=github_url)
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
    return SessionDetailResponse(
        session_id=session.id,
        title=session.title,
        source_repo=session.source_repo,
        source_commit=session.source_commit,
        architecture_plan=ArchitecturePlanResponse(data=plan.data, created_at=plan.created_at) if plan else None,
        images=[
            ImageResponse(
                id=img.id,
                version=img.version,
                file_path=img.file_path,
                prompt=img.prompt,
                reason=img.reason,
                created_at=img.created_at,
            )
            for img in list_images(db, session.id)
        ],
        diagrams=[
            DiagramFileResponse(
                diagram_type=d.diagram_type,
                file_path=d.file_path,
                created_at=d.created_at,
            )
            for d in list_diagrams(db, session.id)
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
    if image_id:
        img = db.get(Image, image_id)
        if not img:
            raise HTTPException(status_code=404, detail="Image not found")
        resolved_path = img.file_path

    if file_path:
        resolved_path = file_path

    if resolved_path:
        path = Path(resolved_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="SVG file not found")
        if path.suffix.lower() != ".svg":
            raise HTTPException(status_code=400, detail="Requested file is not an SVG. Regenerate diagrams as SVG.")
        try:
            svg_text = read_text_file(str(path))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    if svg_text is None or not str(svg_text).strip():
        raise HTTPException(status_code=400, detail="No svg source provided")

    semantic_intent = None
    if image_id:
        img = db.get(Image, image_id)
        if img and getattr(img, "ir_id", None):
            ir = db.get(DiagramIR, img.ir_id)
            if ir and isinstance(ir.ir_json, dict):
                intent_payload = ir.ir_json.get("aesthetic_intent")
                if isinstance(intent_payload, dict):
                    semantic_intent = SemanticAestheticIR.from_dict(intent_payload)

    if animated:
        svg_text = render_svg(svg_text, animated=True, debug=debug, enhanced=enhanced, semantic_intent=semantic_intent, use_v2=enhanced)
    elif enhanced:
        svg_text = render_svg(svg_text, animated=False, debug=debug, enhanced=True, semantic_intent=semantic_intent)

    return JSONResponse(content={"svg": svg_text})


@app.get("/api/debug/modules")
def debug_modules():
    return {
        "svg_parser": svg_parser_module.__file__,
        "plan_generator": plan_module.__file__,
        "css_injector": css_module.__file__,
        "diagram_renderer": renderer_module.__file__,
    }
