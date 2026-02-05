"""Simple DB migration runner for development.

Adds `ir_json` and `plantuml_text` to `diagram_ir_versions` if missing.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from src.utils.config import settings


def main() -> int:
    # Normalize URL for SQLAlchemy (remove +psycopg for psql-like URLs)
    db_url = settings.database_url
    engine = create_engine(db_url)
    alter_ir_json = "ALTER TABLE diagram_ir_versions ADD COLUMN IF NOT EXISTS ir_json JSONB"
    alter_plantuml = "ALTER TABLE diagram_ir_versions ADD COLUMN IF NOT EXISTS plantuml_text TEXT"
    with engine.connect() as conn:
        conn.execute(text(alter_ir_json))
        conn.execute(text(alter_plantuml))
        conn.commit()
    print("Migration applied: ir_json, plantuml_text added (if missing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
