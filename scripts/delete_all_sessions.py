#!/usr/bin/env python3
"""Dangerous helper that wipes all session data from Postgres."""
from __future__ import annotations

import sys
import typer
from sqlalchemy import text

from src.db import engine

TABLES = [
    "plan_executions",
    "styling_audits",
    "diagram_ir_versions",
    "diagram_files",
    "images",
    "messages",
    "plan_records",
    "architecture_plans",
    "sessions",
]
def main(confirm: bool = typer.Option(False, "--confirm", help="Acknowledge that all session data will be deleted.")) -> None:
    if not confirm:
        typer.secho("Refusing to delete data without --confirm", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    stmt = text("TRUNCATE TABLE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE")
    with engine.begin() as conn:
        conn.execute(stmt)

    typer.secho("All session data deleted.", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    try:
        typer.run(main)
    except Exception as exc:
        typer.secho(f"Delete failed: {exc}", fg=typer.colors.RED)
        sys.exit(1)
