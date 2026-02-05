"""POC runner to test intent detection, translators, router, fake renderers, and SVG validation."""
from __future__ import annotations

import json
from src.intent.intent_detector import detect_intent
from src.ir.schemas import StructuralIR, ArchitectureIR, StoryIR, SequenceIR
from src.translation.translators import (
    structural_to_mermaid,
    structural_to_structurizr,
    structural_to_plantuml,
)
from src.renderers.router_simple import choose_renderer
from src.renderers import fake_renderers
from src.renderers.validator import validate_neutral_svg


def structural_from_architecture_example() -> StructuralIR:
    s = StructuralIR()
    s.nodes = [
        {"id": "User", "label": "User", "type": "Actor"},
        {"id": "API", "label": "API Gateway", "type": "System"},
        {"id": "Service", "label": "Auth Service", "type": "Service"},
        {"id": "DB", "label": "User DB", "type": "DataStore"},
    ]
    s.edges = [
        {"source": "User", "target": "API", "label": "requests"},
        {"source": "API", "target": "Service", "label": "auth"},
        {"source": "Service", "target": "DB", "label": "reads/writes"},
    ]
    return s


def run_test_case(name: str, text: str = None, github_url: str = None, structural: StructuralIR = None):
    print(f"\n=== Test: {name} ===")
    intent = detect_intent(text=text, github_url=github_url, has_files=False)
    print("Intent:", intent)
    renderer, reason = choose_renderer(intent)
    print("Renderer chosen:", renderer, "-", reason)

    # Build structural IR if not provided
    if structural is None:
        structural = structural_from_architecture_example()

    # Translate deterministically
    if renderer == "mermaid":
        inp = structural_to_mermaid(structural)
        ok, svg = fake_renderers.render_mermaid(inp)
    elif renderer == "structurizr":
        inp = structural_to_structurizr(structural)
        ok, svg = fake_renderers.render_structurizr(inp)
    else:
        inp = structural_to_plantuml(structural)
        ok, svg = fake_renderers.render_plantuml(inp)

    print("Renderer input preview:\n", (inp[:400] + "...") if len(inp) > 400 else inp)
    valid, msg = validate_neutral_svg(svg)
    print("SVG validation:", valid, msg)
    if valid:
        print("SVG sample:\n", svg[:400])


def main():
    # Test 1 — GitHub Repo
    run_test_case("GitHub Repo", github_url="https://github.com/RJD02/job-portal-go")

    # Test 2 — Architecture Text
    run_test_case("Architecture Text", text="User -> API -> Service -> DB")

    # Test 3 — Story
    story = (
        "Alice walked into the office. She submitted a job application. "
        "The system notified Bob. Later, the applicant received an email."
    )
    run_test_case("Story", text=story)

    # Test 4 — Evolution (Animate this diagram) — should reuse same diagram
    # For POC we simulate by re-running with same structural IR and an "animate" hint
    struct = structural_from_architecture_example()
    run_test_case("Animate", text="Animate this diagram", structural=struct)


if __name__ == "__main__":
    main()
