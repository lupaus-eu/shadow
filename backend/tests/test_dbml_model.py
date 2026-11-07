"""The committed DBML model matches the migrated schema (docs/architecture/dbml/shadow.dbml)."""
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.dbml import TABLE_GROUPS, render_dbml

DBML = Path(__file__).resolve().parents[2] / "docs" / "architecture" / "dbml" / "shadow.dbml"


def test_the_dbml_model_is_current(database_url) -> None:
    engine = create_engine(database_url)
    tables = {name for name in inspect(engine).get_table_names() if name != "alembic_version"}
    grouped = {name for members in TABLE_GROUPS.values() for name in members}
    assert tables - grouped == set(), "add new tables to TABLE_GROUPS in app/dbml.py"
    assert grouped - tables == set(), "remove dropped tables from TABLE_GROUPS in app/dbml.py"
    rendered = render_dbml(engine)
    if os.getenv("UPDATE_DBML"):
        DBML.parent.mkdir(parents=True, exist_ok=True)
        DBML.write_text(rendered)
    assert DBML.exists() and DBML.read_text() == rendered, "DBML is stale: run `UPDATE_DBML=1 ../.venv/bin/python -m pytest -q tests/test_dbml_model.py` in backend/"
