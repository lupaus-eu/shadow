"""Render the migrated PostgreSQL schema as DBML (docs/architecture/dbml/shadow.dbml).

The DBML model is generated, never edited by hand: `tests/test_dbml_model.py`
fails when the committed file differs from the schema after `alembic upgrade
head`, and `UPDATE_DBML=1` rewrites it. Row-level security is summarized in
each table's note, since DBML has no syntax for it.
"""
import re

from sqlalchemy import Engine, inspect, text

# Domain groups for the diagram; every table must be listed (the test checks this).
TABLE_GROUPS: dict[str, list[str]] = {
    "identity": ["user_accounts", "user_sessions", "oidc_login_attempts", "platform_roles", "platform_enrollments"],
    "organization": ["organizations", "organization_memberships", "organization_invitations"],
    "billing": ["organization_seat_changes", "organization_seat_previews", "stripe_webhook_events"],
    "legal": ["legal_acceptances", "legal_announcements"],
    "model_graph": ["models", "model_versions", "nodes", "connections"],
    "metamodel": ["node_types", "connection_types", "allowed_connections"],
    "metrics": ["metrics", "metric_values"],
    "simulation_analysis": ["simulations", "simulation_points", "recommendations"],
    "notifications": ["notifications", "notification_preferences"],
    "operations": ["audit_events", "background_jobs", "outbox_messages", "support_access_requests"],
}


# Types DBML accepts without quotes, such as uuid or varchar(120).
PLAIN_TYPE = re.compile(r"[a-z0-9_]+(\(\d+(,\d+)?\))?")


def _quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def render_dbml(engine: Engine) -> str:
    inspector = inspect(engine)
    tables = sorted(name for name in inspector.get_table_names() if name != "alembic_version")
    with engine.connect() as connection:
        security = {row.relname: (row.relrowsecurity, row.relforcerowsecurity) for row in connection.execute(text("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace"))}
        policies: dict[str, list[str]] = {}
        for row in connection.execute(text("SELECT tablename, policyname, permissive, cmd FROM pg_policies WHERE schemaname = 'public' ORDER BY tablename, policyname")):
            kind = "" if row.permissive == "PERMISSIVE" else " (restrictive)"
            policies.setdefault(row.tablename, []).append(f"{row.policyname}{kind} {row.cmd.lower()}")
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    lines = [
        "// Shadow PostgreSQL schema, generated from the migrated database by backend/app/dbml.py.",
        f"// Alembic revision {revision}. Do not edit by hand: run `UPDATE_DBML=1 pytest tests/test_dbml_model.py` in backend/.",
        "",
        "Project shadow {",
        "  database_type: 'PostgreSQL'",
        "  Note: 'Shadow application database. Tenant tables carry organization_id and PostgreSQL row-level security (ADR-0012); see docs/architecture/database.md.'",
        "}",
        "",
    ]
    refs: list[str] = []
    for table in tables:
        pk = set(inspector.get_pk_constraint(table).get("constrained_columns") or [])
        uniques = [constraint["column_names"] for constraint in inspector.get_unique_constraints(table)]
        single_unique = {columns[0] for columns in uniques if len(columns) == 1}
        lines.append(f"Table {table} {{")
        for column in inspector.get_columns(table):
            settings = []
            if column["name"] in pk and len(pk) == 1: settings.append("pk")
            if not column["nullable"] and column["name"] not in pk: settings.append("not null")
            if column["name"] in single_unique: settings.append("unique")
            if column.get("default") is not None: settings.append(f"default: `{column['default']}`")
            rendered = f" [{', '.join(settings)}]" if settings else ""
            type_name = column["type"].compile(dialect=engine.dialect).lower()
            lines.append(f"  {column['name']} {type_name if PLAIN_TYPE.fullmatch(type_name) else f'\"{type_name}\"'}{rendered}")
        indexes = []
        if len(pk) > 1:
            indexes.append(f"    ({', '.join(sorted(pk))}) [pk]")
        for columns in uniques:
            if len(columns) > 1:
                indexes.append(f"    ({', '.join(columns)}) [unique]")
        for index in sorted(inspector.get_indexes(table), key=lambda item: item["name"]):
            if index.get("duplicates_constraint"):
                continue
            parts = [f"`{expression}`" for expression in index.get("expressions") or []] if index.get("expressions") else list(index["column_names"])
            flags = ["unique"] if index.get("unique") else []
            flags.append(f"name: {_quote(index['name'])}")
            indexes.append(f"    ({', '.join(parts)}) [{', '.join(flags)}]" if len(parts) > 1 or index.get("expressions") else f"    {parts[0]} [{', '.join(flags)}]")
        if indexes:
            lines += ["", "  indexes {", *indexes, "  }"]
        note = []
        checks = sorted(f"{item['name']}: {item['sqltext']}" for item in inspector.get_check_constraints(table))
        if checks: note.append("Checks: " + "; ".join(checks))
        enabled, forced = security.get(table, (False, False))
        if enabled:
            note.append(f"RLS {'forced' if forced else 'enabled'}: " + ", ".join(policies.get(table, [])))
        if note:
            lines += ["", f"  Note: {_quote('. '.join(note))}"]
        lines += ["}", ""]
        for key in inspector.get_foreign_keys(table):
            delete = (key.get("options") or {}).get("ondelete")
            source = key["constrained_columns"]
            target = key["referred_columns"]
            left = f"{table}.{source[0]}" if len(source) == 1 else f"{table}.({', '.join(source)})"
            right = f"{key['referred_table']}.{target[0]}" if len(target) == 1 else f"{key['referred_table']}.({', '.join(target)})"
            refs.append(f"Ref: {left} > {right}" + (f" [delete: {delete.lower()}]" if delete else ""))
    lines += sorted(set(refs))
    lines.append("")
    for group, members in TABLE_GROUPS.items():
        present = [name for name in members if name in tables]
        if present:
            lines += [f"TableGroup {group} {{", *[f"  {name}" for name in present], "}", ""]
    return "\n".join(lines).rstrip("\n") + "\n"
