from src.ir.semantic_ir import SemanticIR, Component, Relationship
from src.ir.semantic_clustering import cluster_ir


def make_ir_with_examples():
    comps = [
        Component(id="postgres_1", name="Postgres Main", type="data_store"),
        Component(id="spark_1", name="Spark Cluster", type="service"),
        Component(id="trino_1", name="Trino Query", type="service"),
        Component(id="vault_1", name="Vault", type="security"),
        Component(id="prom_1", name="Prometheus", type="observability"),
        Component(id="isolated_1", name="Legacy Tool", type="service"),
        Component(id="isolated_2", name="Another Tool", type="service"),
        Component(id="isolated_3", name="Yet Another", type="service"),
        Component(id="isolated_4", name="Isolated 4", type="service"),
        Component(id="isolated_5", name="Isolated 5", type="service"),
    ]
    rels = [
        Relationship(source="web_app", target="spark_1"),
        Relationship(source="web_app", target="trino_1"),
        Relationship(source="ingress", target="postgres_1"),
        Relationship(source="svc_x", target="prom_1"),
    ]
    ir = SemanticIR(id="test", title="Test", components=comps, relationships=rels)
    return ir


def test_clusters_created_and_children_moved():
    ir = make_ir_with_examples()
    new_ir = cluster_ir(ir, min_isolated_trigger=3)
    # Expect at least Compute Layer and Storage/Security groups
    groups = {b.name: b for b in new_ir.boundaries}
    assert any("Compute" in name or "Compute Layer" == name for name in groups.keys()) or any("Shared" in name for name in groups.keys())
    # Check that vault moved into Security Layer if present
    has_security = any("Security" in name for name in groups.keys())
    assert has_security
    # No leaf node should remain without incoming edge or group membership
    comp_ids = {c.id for c in new_ir.components}
    children_in_groups = set(sum([b.children for b in new_ir.boundaries], []))
    nodes_with_in = set(r.target for r in new_ir.relationships)
    leaf_without_in_or_group = [cid for cid in comp_ids if cid not in children_in_groups and cid not in nodes_with_in]
    assert len(leaf_without_in_or_group) == 0
