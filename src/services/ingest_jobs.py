"""Background ingestion job queue and orchestration."""
from __future__ import annotations

import queue
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID

from sqlalchemy import select

from src.db import SessionLocal
from src.db_models import IngestJob, Session as SessionRecord
from src.services.session_service import ingest_input, handle_message, get_session


@dataclass
class IngestPayload:
    job_id: UUID


_JOB_QUEUE: queue.Queue[IngestPayload] = queue.Queue()
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def normalize_repo_url(repo_url: str) -> str:
    parsed = urlparse((repo_url or "").strip())
    cleaned = parsed._replace(fragment="", query="")
    return urlunparse(cleaned).rstrip("/")


def resolve_remote_commit(repo_url: str) -> str | None:
    normalized = normalize_repo_url(repo_url)
    if not normalized:
        return None
    try:
        res = subprocess.run(
            ["git", "ls-remote", normalized, "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        line = (res.stdout or "").strip().splitlines()[0]
        commit = line.split()[0] if line else None
        return commit or None
    except Exception:
        return None


def _build_result_for_session(db, session_id: UUID, ingest_result: dict | None, message_result: dict | None, warnings: list[str] | None = None) -> dict:
    from src.services.session_service import list_images, list_messages

    images = list_images(db, session_id)
    messages = list_messages(db, session_id)
    diagrams = [
        {
            "id": str(img.id),
            "version": img.version,
            "file_path": img.file_path,
            "reason": img.reason,
            "ir_id": str(img.ir_id) if getattr(img, "ir_id", None) else None,
        }
        for img in images
    ]
    return {
        "session_id": str(session_id),
        "ingest": ingest_result or {},
        "message": message_result or {},
        "diagrams": diagrams,
        "warnings": warnings or [],
        "last_assistant_message": next((m.content for m in reversed(messages) if m.role == "assistant" and m.content), ""),
    }


def _process_ingest_job(payload: IngestPayload) -> None:
    db = SessionLocal()
    try:
        job = db.get(IngestJob, payload.job_id)
        if not job:
            return

        job.status = "processing"
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()

        session_record: SessionRecord | None = db.get(SessionRecord, job.session_id) if job.session_id else None
        if not session_record:
            job.status = "failed"
            job.error = "Session not found for ingest job"
            job.updated_at = datetime.utcnow()
            db.add(job)
            db.commit()
            return

        ingest_result = ingest_input(
            db,
            session_record,
            files=None,
            text=f"Analyze repository {job.repo_url} and prepare architecture context.",
            github_url=job.repo_url,
            generate_images=False,
        )

        # Trigger diagram generation from prepared context in background.
        # Keep this prompt deterministic and avoid URL to prevent re-ingest loop.
        generation_prompt = "Generate architecture diagrams from the ingested repository context."
        message_result = handle_message(db, session_record, generation_prompt)

        result = _build_result_for_session(db, session_record.id, ingest_result, message_result)
        job.status = "complete"
        job.result = result
        job.error = None
        job.updated_at = datetime.utcnow()
        db.add(job)
        db.commit()
    except Exception as exc:
        try:
            job = db.get(IngestJob, payload.job_id)
            if job:
                job.status = "failed"
                job.error = str(exc)
                job.updated_at = datetime.utcnow()
                db.add(job)
                db.commit()
        finally:
            pass
    finally:
        db.close()


def _worker_loop() -> None:
    while True:
        payload = _JOB_QUEUE.get()
        try:
            _process_ingest_job(payload)
        finally:
            _JOB_QUEUE.task_done()


def ensure_worker_started() -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        thread = threading.Thread(target=_worker_loop, name="ingest-job-worker", daemon=True)
        thread.start()
        _WORKER_STARTED = True


def enqueue_ingest_job(*, session_id: UUID, repo_url: str, user_prompt: str | None = None) -> IngestJob:
    db = SessionLocal()
    try:
        normalized_url = normalize_repo_url(repo_url)
        commit_hash = resolve_remote_commit(normalized_url)

        if commit_hash:
            existing = db.execute(
                select(IngestJob)
                .where(IngestJob.repo_url == normalized_url)
                .where(IngestJob.commit_hash == commit_hash)
                .where(IngestJob.status == "complete")
                .order_by(IngestJob.updated_at.desc())
            ).scalars().first()
            if existing:
                return existing

        job = IngestJob(
            session_id=session_id,
            repo_url=normalized_url,
            commit_hash=commit_hash,
            status="queued",
            result={"user_prompt": user_prompt} if user_prompt else None,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        _JOB_QUEUE.put(IngestPayload(job_id=job.id))
        return job
    finally:
        db.close()


def get_job(job_id: UUID) -> IngestJob | None:
    db = SessionLocal()
    try:
        return db.get(IngestJob, job_id)
    finally:
        db.close()
