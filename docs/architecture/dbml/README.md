# Database model (DBML)

[`shadow.dbml`](shadow.dbml) describes the Shadow PostgreSQL schema
in [DBML](https://dbml.dbdiagram.io). Open it in dbdiagram.io, dbdocs, or any
DBML viewer.

## What it contains

- Every table after `alembic upgrade head`, with column types, defaults,
  primary keys, not-null, and unique settings.
- Composite and expression indexes, with their names.
- Foreign keys with their `ON DELETE` actions.
- Check constraints, and each table's row-level security policies, as table
  notes. DBML has no syntax for RLS.
- Table groups by domain: identity, organization, billing, legal, model graph, metamodel,
  metrics, simulation and analysis, notifications, and operations.

The Authentik database is separate (ADR-0011) and is not modelled here.

## It is generated, never hand-edited

- **Source:** `backend/app/dbml.py` renders the file from the migrated
  database. `backend/tests/test_dbml_model.py` fails when the committed file
  differs from the schema, or when a table is missing from a domain group.
- **After a migration,** regenerate the file and commit it with the
  migration:

  ```bash
  make dbml
  ```

  This command runs `UPDATE_DBML=1 ../.venv/bin/python -m pytest -q tests/test_dbml_model.py`
  in `backend/`.
- **Validation:** `make models` also checks that the DBML parses, with the
  pinned `@dbml/cli@10.2.0`.

Narrative and decisions about the schema stay in
[`../database.md`](../database.md).
