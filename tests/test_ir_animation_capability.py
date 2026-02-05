from src.ir.semantic_ir import SemanticIR, Component, Relationship


def test_ir_supports_order_and_state():
    ir = SemanticIR(id="1", title="T")
    ir.components.append(Component(id="a", name="A", state="idle"))
    ir.components.append(Component(id="b", name="B", state="active"))
    ir.relationships.append(Relationship(source="a", target="b", order=1, label="step1"))
    assert any(getattr(r, "order", None) is not None for r in ir.relationships)
    assert any(getattr(c, "state", None) is not None for c in ir.components)
