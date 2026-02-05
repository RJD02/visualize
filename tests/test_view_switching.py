from src.ir.semantic_ir import SemanticIR, Component, Relationship
from src.ir.plantuml_adapter import ir_to_plantuml


def test_view_switching_same_ir():
    ir = SemanticIR(id="1", title="T")
    ir.components.append(Component(id="a", name="A"))
    ir.components.append(Component(id="b", name="B"))
    ir.relationships.append(Relationship(source="a", target="b", label="r"))
    p_context = ir_to_plantuml(ir, diagram_type="context")
    p_container = ir_to_plantuml(ir, diagram_type="container")
    assert p_context != "" and p_container != ""
    # both generated from same IR; no IR regen required per change
