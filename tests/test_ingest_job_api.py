from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

import src.server as server


class _DummyDb:
    pass


def _override_get_db():
    yield _DummyDb()


def test_enqueue_ingest_job_returns_queued(monkeypatch):
    app = server.app
    app.dependency_overrides[server.get_db] = _override_get_db

    session_id = uuid4()
    job_id = uuid4()

    monkeypatch.setattr(server, "get_session", lambda db, sid: None)
    monkeypatch.setattr(server, "create_session", lambda db: SimpleNamespace(id=session_id))
    monkeypatch.setattr(
        server,
        "enqueue_ingest_job",
        lambda **kwargs: SimpleNamespace(id=job_id, status="queued", result=None, error=None),
    )

    client = TestClient(app)
    resp = client.post("/api/ingest", json={"repo_url": "https://github.com/org/repo"})

    app.dependency_overrides.clear()

    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == str(job_id)
    assert body["session_id"] == str(session_id)
    assert body["status"] == "queued"


def test_ingest_job_status_transition(monkeypatch):
    app = server.app

    statuses = ["queued", "processing", "complete"]
    now = datetime.now(timezone.utc)
    job_id = uuid4()
    session_id = uuid4()

    def _fake_get_job(_job_id):
        status = statuses.pop(0) if statuses else "complete"
        return SimpleNamespace(
            id=job_id,
            session_id=session_id,
            repo_url="https://github.com/org/repo",
            commit_hash="abc123",
            status=status,
            result={"diagrams": []} if status == "complete" else None,
            error=None,
            created_at=now,
            updated_at=now,
        )

    monkeypatch.setattr(server, "get_job", _fake_get_job)

    client = TestClient(app)
    first = client.get(f"/api/ingest/{job_id}")
    second = client.get(f"/api/ingest/{job_id}")
    third = client.get(f"/api/ingest/{job_id}")

    assert first.status_code == 200
    assert first.json()["status"] == "queued"
    assert second.status_code == 200
    assert second.json()["status"] == "processing"
    assert third.status_code == 200
    assert third.json()["status"] == "complete"
    assert third.json()["result"] is not None
