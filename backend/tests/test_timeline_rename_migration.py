"""Migration 0065 renames event to Change and change to Edit; the guard keeps the old words out (tech-change-terminology ticket 01).

A model with a Base line, a Scenario, changes and edits is made through the application at head, the schema is moved
back to 0064 (old names), more rows are written under the old names, and the schema is moved up to 0065 again: every
row survives, the constraints work under the new names, no object of the timeline tables keeps an old name, and the
downgrade gives the old names back. The Activity API reads both the legacy ``event.*`` and the new ``change.*`` audit actions.
"""
import re
from contextlib import ExitStack
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.audit import AuditEventDraft, record_audit_event
from app.database import RequestContext, transaction_session
from test_models_graph import _graph, _tenant, _types

BACKEND = Path(__file__).resolve().parents[1]
TIMELINE_TABLES = ("model_lines", "timeline_events", "event_changes", "timeline_changes", "change_edits", "node_positions")


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _config(database_url: str) -> Config:
    config = Config(BACKEND / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _object_names(connection) -> set[str]:
    owners = list(TIMELINE_TABLES)
    names = {row[0] for row in connection.execute(text("SELECT conname FROM pg_constraint WHERE conrelid::regclass::text = ANY(:o)"), {"o": owners})}
    names |= {row[0] for row in connection.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = ANY(:o)"), {"o": owners})}
    names |= {row[0] for row in connection.execute(text("SELECT policyname FROM pg_policies WHERE tablename = ANY(:o)"), {"o": owners})}
    names |= {row[0] for row in connection.execute(text("SELECT relname FROM pg_class WHERE relkind = 'S' AND relname LIKE 'timeline_%'"))}
    return names


def _tables(connection) -> set[str]:
    return {row[0] for row in connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}


def _snapshot(connection, model_id: str, changes: str, edits: str, change_column: str, branch_column: str) -> dict:
    mine = {"model": model_id}
    return {
        "changes": [tuple(row) for row in connection.execute(text(f"SELECT id, line_id, occurred_on, seq, title, version FROM {changes} WHERE model_id = :model ORDER BY seq"), mine)],
        "edits": [tuple(row) for row in connection.execute(text(f"SELECT id, {change_column}, position, op, element_id, payload FROM {edits} WHERE {change_column} IN (SELECT id FROM {changes} WHERE model_id = :model) ORDER BY {change_column}, position"), mine)],
        "lines": [tuple(row) for row in connection.execute(text(f"SELECT id, kind, parent_line_id, {branch_column}, name FROM model_lines WHERE model_id = :model ORDER BY name"), mine)],
    }


def test_the_rename_keeps_every_row_and_constraint_and_the_downgrade_gives_the_old_names_back(database_url: str, stack: ExitStack) -> None:
    _, owner, organization_id, base = _tenant(stack, database_url, "rename-0065")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    graph = _graph(owner, base, model_id)
    types = _types(graph)
    baseline = graph["line"]["id"]
    initial = owner.get(f"{path}/lines/{baseline}/changes").json()[-1]["id"]
    assert owner.post(f"{path}/changes/{initial}/nodes", json={"node_type_id": types["product"], "name": "App"}).status_code == 201
    scenario = owner.post(f"{path}/lines", json={"name": "What if", "branch_change_id": initial}).json()["id"]
    node = {"op": "add_node", "element_id": str(uuid4()), "payload": {"node_type_id": types["person"], "name": "Ada", "description": None}}
    own = owner.post(f"{path}/lines/{scenario}/changes", json={"occurred_on": "2099-01-01", "title": "Own", "edits": [node]})
    assert own.status_code == 201
    stack.close()

    engine = create_engine(database_url)
    config = _config(database_url)
    try:
        with engine.connect() as connection:
            at_head = _snapshot(connection, model_id, "timeline_changes", "change_edits", "change_id", "branch_change_id")
            assert _tables(connection) >= {"timeline_changes", "change_edits"} and not _tables(connection) & {"timeline_events", "event_changes"}
        assert len(at_head["changes"]) == 2 and len(at_head["edits"]) >= 2 and len(at_head["lines"]) == 2

        command.downgrade(config, "0064")
        with engine.begin() as connection:
            assert _tables(connection) >= {"timeline_events", "event_changes"} and not _tables(connection) & {"timeline_changes", "change_edits"}
            assert _snapshot(connection, model_id, "timeline_events", "event_changes", "event_id", "branch_event_id") == at_head
            names = _object_names(connection)
            assert {"ix_timeline_events_line_order", "fk_model_lines_branch_event", "uq_event_changes_event_position", "timeline_events_policy", "event_changes_policy", "timeline_events_seq_seq"} <= names
            assert not [name for name in names if "change" in name and "changed" not in name and "event" not in name]
            # A row written under the old names must survive the upgrade.
            old_change, old_edit = uuid4(), uuid4()
            connection.execute(text("INSERT INTO timeline_events (id, organization_id, model_id, line_id, occurred_on, title) VALUES (:id, :org, :model, :line, '2099-02-01', 'Old name')"), {"id": old_change, "org": organization_id, "model": model_id, "line": scenario})
            connection.execute(text("INSERT INTO event_changes (id, organization_id, event_id, position, op, element_id, payload) VALUES (:id, :org, :event, 0, 'add_node', :element, :payload)"), {"id": old_edit, "org": organization_id, "event": old_change, "element": uuid4(), "payload": '{"node_type_id": "%s", "name": "Old"}' % types["person"]})
            at_old = _snapshot(connection, model_id, "timeline_events", "event_changes", "event_id", "branch_event_id")

        command.upgrade(config, "0065")
        with engine.begin() as connection:
            assert _snapshot(connection, model_id, "timeline_changes", "change_edits", "change_id", "branch_change_id") == at_old
            names = _object_names(connection)
            assert not [name for name in names if "event" in name], names
            assert {"ix_timeline_changes_line_order", "fk_model_lines_branch_change", "uq_change_edits_change_position", "timeline_changes_policy", "change_edits_policy", "timeline_changes_seq_seq"} <= names
            policies = {row[0] for row in connection.execute(text("SELECT policyname FROM pg_policies WHERE tablename IN ('timeline_changes', 'change_edits')"))}
            assert len(policies) == 12 and not [name for name in policies if "event" in name]
            forced = connection.execute(text("SELECT count(*) FROM pg_class WHERE relname IN ('timeline_changes', 'change_edits') AND relforcerowsecurity")).scalar_one()
            assert forced == 2
            new_change = uuid4()
            connection.execute(text("INSERT INTO timeline_changes (id, organization_id, model_id, line_id, occurred_on, title) VALUES (:id, :org, :model, :line, '2099-03-01', 'New name')"), {"id": new_change, "org": organization_id, "model": model_id, "line": scenario})
            seq = connection.execute(text("SELECT seq FROM timeline_changes WHERE id = :id"), {"id": new_change}).scalar_one()
            assert seq > max(row[3] for row in at_old["changes"])  # the identity sequence keeps counting

        def refused(statement: str, **params) -> None:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text(statement), params)

        edit = "INSERT INTO change_edits (id, organization_id, change_id, position, op, element_id, payload) VALUES (:id, :org, :change, :position, :op, :element, '{}')"
        refused(edit, id=uuid4(), org=organization_id, change=old_change, position=0, op="add_node", element=uuid4())  # unique (change, position)
        refused(edit, id=uuid4(), org=organization_id, change=old_change, position=1, op="rename_everything", element=uuid4())  # check on the operation
        refused(edit, id=uuid4(), org=organization_id, change=uuid4(), position=0, op="add_node", element=uuid4())  # foreign key to the change
        refused("DELETE FROM timeline_changes WHERE id = :id", id=initial)  # the Scenario branches from it (fk_model_lines_branch_change, RESTRICT)
        refused("INSERT INTO timeline_changes (id, organization_id, model_id, line_id, occurred_on, title) VALUES (:id, :org, :model, :line, '2099-04-01', '  ')", id=uuid4(), org=organization_id, model=model_id, line=scenario)
        with engine.begin() as connection:  # deleting a change takes its edits with it
            connection.execute(text("DELETE FROM timeline_changes WHERE id = :id"), {"id": old_change})
            assert connection.execute(text("SELECT count(*) FROM change_edits WHERE id = :id"), {"id": old_edit}).scalar_one() == 0

        command.downgrade(config, "0064")
        with engine.connect() as connection:
            assert not [name for name in _object_names(connection) if "change" in name and "changed" not in name and "event" not in name]
            assert connection.execute(text("SELECT count(*) FROM timeline_events WHERE model_id = :model"), {"model": model_id}).scalar_one() == len(at_head["changes"]) + 1  # the new row, the old one is deleted
    finally:
        command.upgrade(config, "head")
        engine.dispose()


def test_activity_reads_legacy_event_actions_and_new_change_actions(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, base = _tenant(stack, database_url, "rename-activity")
    factory = application.state.session_factory
    with transaction_session(factory, RequestContext(user_account_id=uuid4(), organization_id=UUID(organization_id))) as session:
        for action, target in (("event.created", "event"), ("change.created", "change")):
            record_audit_event(session, AuditEventDraft(action=action, target_type=target, target_id=uuid4(), request_id=f"rename-{action}", change_summary={}))
    legacy = owner.get(f"{base}/audit-events", params={"prefix": "event"}).json()["items"]
    current = owner.get(f"{base}/audit-events", params={"prefix": "change"}).json()["items"]
    exact = owner.get(f"{base}/audit-events", params={"action": "change.created"}).json()["items"]
    assert [(item["action"], item["target_type"]) for item in legacy] == [("event.created", "event")]
    assert [(item["action"], item["target_type"]) for item in current] == [("change.created", "change")]
    assert [item["action"] for item in exact] == ["change.created"]


STALE = re.compile(
    r"timeline_events|event_changes|EventRecord|TimelineEvent|EventChange|\b(?:add|update|delete|list)_event\b|branch_event|event_count|LIMIT_EVENTS_PER_LINE|"
    r"\bevents_of\b|event_rows|\bChangeInvalid\b|\bapply_changes?\b|\bchange_counts\b|timeline_event_routes|/events\b"
)
# Files where the dated item of a line is the subject: the word "event" may only appear as part of the Audit Event names.
TIMELINE_FILES = (
    "app/timeline/*.py", "app/timeline_*.py", "app/mcp_server/model_tools.py", "app/model_routes.py", "app/metamodel_routes.py",
    "app/metric_routes.py", "app/limits.py", "app/models.py",
)
# models.py also holds the Stripe webhook table and the Audit Event table; these are not the timeline.
ALLOWED_EVENT_WORDS = re.compile(r"\w*(?:[Aa]udit_?[Ee]vent|AuditEvent|Stripe|stripe|subscription_event)\w*|audit-events")
MODELS_ALLOWED_LINE = re.compile(r"event_id|event_type")


def test_the_old_timeline_vocabulary_does_not_return_to_the_application() -> None:
    offenders = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if STALE.search(line):
                offenders.append(f"{path.relative_to(BACKEND)}:{number}: {line.strip()[:100]}")
    assert not offenders, "\n".join(offenders)


def test_the_timeline_code_has_no_event_words_except_audit_and_stripe_names() -> None:
    offenders = []
    for pattern in TIMELINE_FILES:
        for path in sorted(BACKEND.glob(pattern)):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if path.name == "models.py" and MODELS_ALLOWED_LINE.search(line):
                    continue
                if re.search(r"(?i)event", ALLOWED_EVENT_WORDS.sub("", line)):
                    offenders.append(f"{path.relative_to(BACKEND)}:{number}: {line.strip()[:100]}")
    assert not offenders, "\n".join(offenders)
