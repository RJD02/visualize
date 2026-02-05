from src.ir.semantic_ir import SemanticIR, Component, Relationship
from src.ir.plantuml_adapter import ir_to_plantuml


def test_plantuml_is_deterministic():
    ir1 = SemanticIR(id="1", title="T")
    ir1.components.append(Component(id="a", name="A"))
    ir1.components.append(Component(id="b", name="B"))
    ir1.relationships.append(Relationship(source="a", target="b", label="call"))
    p1 = ir_to_plantuml(ir1, diagram_type="container")
    p2 = ir_to_plantuml(ir1, diagram_type="container")
    assert p1 == p2
