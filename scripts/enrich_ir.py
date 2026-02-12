#!/usr/bin/env python3
"""CLI harness to enrich minimal IR JSON via the v34 Codex prompt."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from jsonschema import Draft202012Validator, ValidationError

from src.utils.config import settings
from src.utils.openai_client import get_openai_client

app = typer.Typer(add_completion=False, help=__doc__)

DEFAULT_SPEC_PATH = Path("specs/specs_v34_ir_enrichment_prompt.md")
DEFAULT_SCHEMA_PATH = Path("specs/ir_enriched_schema_v1.json")


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"Input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON in {path}: {exc}") from exc


def _load_prompt(spec_path: Path) -> str:
    try:
        content = spec_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"Spec prompt not found at {spec_path}") from exc
    return content.strip()


def _validate_schema(payload: dict, schema_path: Path) -> None:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise typer.BadParameter(f"Schema not found at {schema_path}") from exc
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Schema file is invalid JSON: {exc}") from exc

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        formatted = "\n".join(
            f"- {'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}" for err in errors
        )
        raise typer.BadParameter(f"Enriched IR failed schema validation:\n{formatted}")


def _call_llm(prompt: str, input_ir: dict) -> dict:
    client = get_openai_client()
    serialized_ir = json.dumps(input_ir, indent=2, ensure_ascii=False)
    user_message = (
        "INPUT_IR:\n" +
        "```json\n" + serialized_ir + "\n```\n" +
        "Return enriched JSON only as OUTPUT_JSON."
    )
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        # Try to salvage JSON if wrapped in markdown fences
        stripped = content.strip().strip("`")
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            raise RuntimeError(f"LLM response was not valid JSON: {exc}\nContent:\n{content}") from exc


@app.command()
def main(
    input_path: Path = typer.Argument(..., help="Path to minimal IR JSON file."),
    output_path: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional output path. Defaults to outputs/<stem>_enriched.json",
    ),
    spec_path: Path = typer.Option(
        DEFAULT_SPEC_PATH,
        "--spec",
        help="Path to the enrichment prompt markdown file.",
    ),
    schema_path: Path = typer.Option(
        DEFAULT_SCHEMA_PATH,
        "--schema",
        help="Path to the enriched IR JSON schema.",
    ),
    dry_run: bool = typer.Option(False, help="Print enriched JSON instead of writing to disk."),
) -> None:
    """Enrich a minimal IR using the v34 prompt and validate the result."""
    if not settings.openai_api_key:
        raise typer.BadParameter("OPENAI_API_KEY is not set; cannot call enrichment prompt.")

    input_ir = _load_json(input_path)
    prompt = _load_prompt(spec_path)
    typer.echo(f"[enrich_ir] Loaded input IR from {input_path}")

    enriched = _call_llm(prompt, input_ir)
    # stamp timestamp if missing to meet schema expectations
    metadata = enriched.setdefault("metadata", {})
    metadata.setdefault("generated_by", "scripts.enrich_ir")
    metadata.setdefault("spec_version", "v34")
    metadata.setdefault("timestamp", datetime.utcnow().isoformat(timespec="seconds") + "Z")
    metadata.setdefault("validation", [])

    _validate_schema(enriched, schema_path)
    typer.echo("[enrich_ir] Enriched IR passed schema validation")

    if dry_run:
        typer.echo(json.dumps(enriched, indent=2, ensure_ascii=False))
        return

    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = output_dir / f"{input_path.stem}_ir_enriched.json"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    typer.echo(f"[enrich_ir] Wrote enriched IR to {output_path}")


if __name__ == "__main__":
    app()
