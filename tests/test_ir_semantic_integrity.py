from src.ir.semantic_ir import SemanticIR, Component, Actor, Relationship


def test_ir_contains_no_layout():
    ir = SemanticIR(id="t1", title="t")
    ir.components.append(Component(id="c1", name="C1"))
    ir.relationships.append(Relationship(source="c1", target="c1", label="self"))
    j = ir.to_json()
    # ensure no layout keys are present as JSON keys
    assert '"x"' not in j and '"y"' not in j and '"width"' not in j and '"height"' not in j
