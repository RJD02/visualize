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


def test_sanitize_mermaid_strips_title_directive():
    """Mermaid flowchart/graph blocks don't support 'title' as a body statement."""
    mermaid_with_title = """graph TD
    title Enterprise Open-Stack Architecture
    A[Service A] --> B[Service B]
    B --> C[(Database)]
"""
    result = validate_and_sanitize(mermaid_with_title, "mermaid")
    assert "title" not in result.sanitized_text
    assert "graph TD" in result.sanitized_text
    assert "A[Service A] --> B[Service B]" in result.sanitized_text
    assert result.blocked_tokens == []


def test_sanitize_mermaid_quotes_labels_with_parentheses():
    """Parentheses inside node labels must be quoted to avoid shape-syntax confusion."""
    mermaid_with_parens = """graph TD
    A[Business Users (BI)] --> B[Data Engineering]
    B --> C{Decision (Final)}
    D["Already Quoted (OK)"] --> E[No Parens]
"""
    result = validate_and_sanitize(mermaid_with_parens, "mermaid")
    # Labels with parens should be quoted
    assert 'A["Business Users (BI)"]' in result.sanitized_text
    assert 'C{"Decision (Final)"}' in result.sanitized_text
    # Already-quoted labels should be left alone
    assert 'D["Already Quoted (OK)"]' in result.sanitized_text
    # Labels without special chars should be untouched
    assert "E[No Parens]" in result.sanitized_text
    assert result.blocked_tokens == []


def test_sanitize_mermaid_quotes_labels_with_braces():
    """Braces inside node labels must be quoted."""
    mermaid_with_braces = """graph LR
    X[Config {json}] --> Y[Output]
"""
    result = validate_and_sanitize(mermaid_with_braces, "mermaid")
    assert 'X["Config {json}"]' in result.sanitized_text
    assert "Y[Output]" in result.sanitized_text
