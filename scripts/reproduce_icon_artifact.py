"""Deterministic reproduction script for icon rendering artifact.

Usage:
    python scripts/reproduce_icon_artifact.py --output out.svg

This script calls the renderer with fixed PlantUML input and writes an SVG/PNG
to the `--output` path. It is intended for local reproduction and CI verification.
"""
from argparse import ArgumentParser
from src.renderer import render_plantuml_svg


def main():
    p = ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()

    plantuml = "@startuml\nAlice -> Bob: Hello\n@enduml"
    out = render_plantuml_svg(plantuml, args.output.replace(".svg", ""))
    print("Wrote:", out)


if __name__ == "__main__":
    main()
