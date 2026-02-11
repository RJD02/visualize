import pytest

from src.tools.diagram_validator import DiagramValidationError, validate_and_sanitize


PLANTUML_ALLOWED = """@startuml
component "Backend" as B
component "DB" as D
B --> D : reads
@enduml"""


PLANTUML_BLOCKED = """!include https://example.com/malicious.puml
@startuml
A -> B
@enduml"""


MERMAID_ALLOWED = """graph LR
  A[Client] --> B[Server]
"""


MERMAID_BLOCKED = """%%{init: {"themeVariables": {"dark": true}}}%%
graph LR
  A --> B
"""


def test_validate_plantuml_allows_basic_components():
    result = validate_and_sanitize(PLANTUML_ALLOWED, "plantuml")
    assert "@startuml" in result.sanitized_text
    assert not result.blocked_tokens


def test_validate_plantuml_blocks_include_directive():
    with pytest.raises(DiagramValidationError) as excinfo:
        validate_and_sanitize(PLANTUML_BLOCKED, "plantuml")
    assert any("include" in token for token in excinfo.value.result.blocked_tokens)


def test_validate_mermaid_blocks_init_sections():
    with pytest.raises(DiagramValidationError) as excinfo:
        validate_and_sanitize(MERMAID_BLOCKED, "mermaid")
    assert any("init" in token for token in excinfo.value.result.blocked_tokens)


def test_validate_mermaid_baseline_passes():
    result = validate_and_sanitize(MERMAID_ALLOWED, "mermaid")
    assert "graph LR" in result.sanitized_text
    assert result.blocked_tokens == []
