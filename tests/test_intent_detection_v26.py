from src.intent.diagram_intent import detect_intent
from src.intent.semantic_to_structural import story_ir_from_text, story_to_structural, sequence_ir_from_text, sequence_to_structural


def test_intent_github_repo_defaults():
    intent = detect_intent("", github_url="https://github.com/RJD02/job-portal-go")
    assert intent.primary == "system_context"
    assert "container" in intent.intents
    assert "component" in intent.intents


def test_intent_story_detection():
    text = "Arjun stood alone under the dim platform lamp. The rain fell again."
    intent = detect_intent(text, github_url=None)
    assert intent.primary == "story"


def test_story_ir_to_structural():
    text = "Arjun walked to the platform. The train arrived."
    story_ir = story_ir_from_text(text)
    structural = story_to_structural(story_ir)
    assert structural.diagram_kind == "flow"
    assert len(structural.nodes) >= 2


def test_sequence_ir_to_structural():
    text = "User -> API -> Service -> DB"
    seq_ir = sequence_ir_from_text(text)
    structural = sequence_to_structural(seq_ir)
    assert structural.diagram_kind == "sequence"
    assert len(structural.edges) >= 2
