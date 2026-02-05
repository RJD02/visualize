from src.ir.semantic_ir import SemanticIR, Component, Actor, Relationship, SystemBoundary
from src.ir.llm_compiler import compile_ir_to_uml


def test_compile_ir_to_uml_basic():
    ir = SemanticIR(id="1", title="T")
    ir.actors.append(Actor(id="user", name="User"))
    ir.components.append(Component(id="svc", name="Service", type="component"))
    ir.boundaries.append(SystemBoundary(id="pkg1", name="Core", children=["svc"]))
    ir.relationships.append(Relationship(source="user", target="svc", label="calls"))

    model = compile_ir_to_uml(ir)
    plant = model.to_plantuml()
    assert "actor \"User\"" in plant
    assert "component \"Service\"" in plant
    assert "calls" in plant
