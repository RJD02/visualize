"""CLI interface."""
from __future__ import annotations

import json
from typing import List, Optional

import typer

from src.orchestrator.adk_workflow import ADKWorkflow

app = typer.Typer(add_completion=False)


@app.command()
def generate(
    file: List[str] = typer.Option(None, "--file", "-f", help="Path to code or .docx file.", show_default=False),
    text: Optional[str] = typer.Option(None, "--text", "-t", help="Paste code/text."),
    output_name: str = typer.Option("diagram", "--output-name"),
):
    """Generate PlantUML and DALL·E outputs."""
    if not file and not text:
        raise typer.BadParameter("Provide --file or --text")
    workflow = ADKWorkflow()
    result = workflow.run(files=file, text=text, output_name=output_name)
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
