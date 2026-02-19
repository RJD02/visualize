from src.ir.relationship_extractor import extract_relationships

def test_connect_a_to_b():
    prompt = "Connect A to B"
    blocks = [{"id": "A"}, {"id": "B"}]
    edges = extract_relationships(prompt, blocks)
    assert len(edges) == 1
    e = edges[0]
    assert e.from_ == "A"
    assert e.to == "B"
    assert e.category == "user_traffic"
    assert e.label == "connect"
    assert e.confidence >= 0.7

def test_replicate_x_to_y():
    prompt = "X replicates to Y"
    blocks = [{"id": "X"}, {"id": "Y"}]
    edges = extract_relationships(prompt, blocks)
    assert len(edges) == 1
    e = edges[0]
    assert e.category == "replication"
    assert e.from_ == "X"
    assert e.to == "Y"

def test_vault_supplies_secrets():
    prompt = "Vault supplies secrets to all services"
    blocks = [{"id": "Vault"}, {"id": "svc1"}, {"id": "svc2"}]
    edges = extract_relationships(prompt, blocks)
    assert len(edges) == 2
    assert all(e.from_ == "Vault" for e in edges)
    assert set(e.to for e in edges) == {"svc1", "svc2"}
    assert all(e.category == "secret_distribution" for e in edges)

def test_observability_connects_all():
    prompt = "Observability connects to all components"
    blocks = [{"id": "Observability"}, {"id": "A"}, {"id": "B"}]
    edges = extract_relationships(prompt, blocks)
    assert len(edges) == 2
    assert all(e.from_ == "Observability" for e in edges)
    assert set(e.to for e in edges) == {"A", "B"}
    assert all(e.category == "user_traffic" for e in edges)
