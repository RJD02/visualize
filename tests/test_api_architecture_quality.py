import os
import sys

from fastapi.testclient import TestClient

# ensure backend src is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend-python", "src")))

from server import app


def test_analyze_architecture_api_basic():
    client = TestClient(app)
    ir = {
        "nodes": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "edges": [{"source": "A", "target": "B"}, {"source": "B", "target": "C"}, {"source": "C", "target": "A"}],
    }
    resp = client.post("/api/analysis/architecture-quality", json={"ir": ir})
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "issues" in data
    assert data["metrics"]["cycles_count"] == 1
