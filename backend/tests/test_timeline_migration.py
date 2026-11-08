"""Migration 0061: versions, graphs, metrics and simulations become lines and events (model-timeline ticket 02).

The seed is built through the application (old version routes still exist), the schema is moved back to
0060 and up to 0061 again, and the replayed state of every line is compared with the old graph.
"""
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.timeline.chain import EventRecord, LineRecord, state_after
from app.timeline.state import Change, Metamodel
from test_metrics import _values
from test_models_graph import _graph, _tenant, _types

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _config(database_url: str) -> Config:
    config = Config(BACKEND / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _node(owner, path, version_id, node_type_id, name, **extra):
    body = {"node_type_id": node_type_id, "name": name, **extra}
    if version_id:
        body["version_id"] = version_id
    created = owner.post(f"{path}/nodes", json=body)
    assert created.status_code == 201, created.text
    return created.json()


def _seed(owner, base) -> dict:
    """A Model with a graph, metrics, a simulation and forks of every shape; returns the ids that matter."""
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    types = _types(_graph(owner, base, model_id))
    baseline = _graph(owner, base, model_id)["version"]["id"]
    app = _node(owner, path, None, types["product"], "App", description="The product", x=10, y=20)
    journey = _node(owner, path, None, types["journey"], "Onboarding", x=30, y=40)
    goal = _node(owner, path, None, types["contract"], "Terms")
    for source, target in ((app, journey), (app, goal)):
        assert owner.post(f"{path}/connections", json={"connection_type_id": types["c:features_in"] if target is journey else types["c:is_composed_of"], "source_node_id": source["id"], "target_node_id": target["id"]}).status_code == 201, "seed connection"
    metrics = f"{path}/versions/{baseline}/metrics"
    revenue = owner.post(metrics, json={"key": "revenue", "name": "Revenue", "unit": "EUR", "node_id": app["id"]}).json()
    owner.post(metrics, json={"key": "double", "name": "Double", "formula": "revenue * 2"})
    _values(owner, metrics, revenue["id"], [(f"2025-{m:02d}-01", 100 + m) for m in range(1, 13)])
    assert owner.post(f"{path}/versions/{baseline}/simulations", json={"name": "Base run", "method": "linear", "horizon_months": 3}).status_code == 201

    def fork(name, base_version=None):
        body = {"name": name} | ({"base_version_id": base_version} if base_version else {})
        created = owner.post(f"{path}/versions", json=body)
        assert created.status_code == 201, created.text
        return created.json()["id"]

    def nodes_of(version_id):
        return {item["name"]: item for item in owner.get(path, params={"version_id": version_id}).json()["nodes"]}

    def connections_of(version_id):
        return owner.get(path, params={"version_id": version_id}).json()["connections"]

    # Growth: rename, move, drop one connection, add a node; it has a fork of its own.
    growth = fork("Growth")
    names = nodes_of(growth)
    assert owner.patch(f"{path}/nodes/{names['App']['id']}", json={"expected_version": 1, "name": "App 2", "description": None, "x": 111, "y": 222}).status_code == 200
    connection = next(item for item in connections_of(growth) if item["connection_type_id"] == types["c:is_composed_of"])
    assert owner.delete(f"{path}/connections/{connection['id']}", params={"expected_version": 1}).status_code == 204
    _node(owner, path, growth, types["product"], "Extra", x=5, y=6)
    deeper = fork("Growth deeper", growth)
    names = nodes_of(deeper)
    assert owner.delete(f"{path}/nodes/{names['Onboarding']['id']}", params={"expected_version": 1}).status_code == 204
    extra = nodes_of(deeper)["Extra"]
    added = _node(owner, path, deeper, types["journey"], "Checkout")
    assert owner.post(f"{path}/connections", json={"connection_type_id": types["c:features_in"], "source_node_id": extra["id"], "target_node_id": added["id"]}).status_code == 201
    # Dropping a node takes its connections with it.
    pruned = fork("Pruned")
    assert owner.delete(f"{path}/nodes/{nodes_of(pruned)['Onboarding']['id']}", params={"expected_version": 1}).status_code == 204
    # The baseline moves on after the forks above were made: they lack its new node, so their events remove it.
    _node(owner, path, None, types["person"], "Late")
    # Same as the baseline: no event of its own; a fork of it branches where it branches.
    unchanged = fork("Unchanged")
    below_unchanged = fork("Below unchanged", unchanged)
    owner.post(f"{path}/versions/{below_unchanged}/metrics", json={"key": "own", "name": "Own"})
    return {"org_model": model_id, "baseline": baseline, "growth": growth, "deeper": deeper, "unchanged": unchanged, "below_unchanged": below_unchanged, "pruned": pruned}


def _load(engine):
    with engine.connect() as connection:
        rows = lambda sql: [dict(row._mapping) for row in connection.execute(text(sql))]  # noqa: E731
        return {
            "versions": rows("SELECT * FROM model_versions"),
            "nodes": rows("SELECT * FROM nodes"),
            "connections": rows("SELECT * FROM connections"),
            "lines": rows("SELECT * FROM model_lines"),
            "events": rows("SELECT * FROM timeline_events ORDER BY occurred_on, seq"),
            "changes": rows("SELECT * FROM event_changes ORDER BY event_id, position"),
            "positions": rows("SELECT * FROM node_positions"),
            "node_types": rows("SELECT id, model_id FROM node_types"),
            "connection_types": rows("SELECT id, model_id FROM connection_types"),
            "allowed": rows("SELECT * FROM allowed_connections"),
        }


def _engine_inputs(data, model_id):
    lines = {row["id"]: LineRecord(row["id"], row["parent_line_id"], row["branch_event_id"]) for row in data["lines"] if row["model_id"] == model_id}
    changes: dict = {}
    for row in data["changes"]:
        changes.setdefault(row["event_id"], []).append(Change(row["op"], row["element_id"], row["payload"]))
    events: dict = {}
    for row in data["events"]:
        if row["model_id"] == model_id:
            events.setdefault(row["line_id"], []).append(EventRecord(row["id"], row["line_id"], row["occurred_on"], row["seq"], row["title"], tuple(changes.get(row["id"], ()))))
    metamodel = Metamodel(
        frozenset(row["id"] for row in data["node_types"] if row["model_id"] == model_id),
        frozenset(row["id"] for row in data["connection_types"] if row["model_id"] == model_id),
        frozenset((row["connection_type_id"], row["source_node_type_id"], row["target_node_type_id"]) for row in data["allowed"] if row["model_id"] == model_id),
    )
    return lines, events, metamodel


def _element_ids(data) -> dict:
    """The element id the migration should have given each old node: its origin's, if the base still has it."""
    versions = {row["id"]: row for row in data["versions"]}
    nodes = {row["id"]: row for row in data["nodes"]}
    by_version: dict = {}
    for node in data["nodes"]:
        by_version.setdefault(node["version_id"], set()).add(node["id"])
    cache: dict = {}

    def element(node_id):
        if node_id not in cache:
            node = nodes[node_id]
            version = versions[node["version_id"]]
            origin = node["origin_node_id"]
            base = version["base_version_id"]
            if version["is_baseline"] or origin is None or origin not in nodes or base is None or origin not in by_version.get(base, ()):
                cache[node_id] = node_id
            else:
                cache[node_id] = element(origin)
        return cache[node_id]

    return {node_id: element(node_id) for node_id in nodes}


def _assert_replay_equals_old_graph(data, version_id, model_id) -> None:
    lines, events, metamodel = _engine_inputs(data, model_id)
    state = state_after(lines, events, metamodel, version_id)
    element = _element_ids(data)
    old_nodes = [row for row in data["nodes"] if row["version_id"] == version_id]
    assert set(state.nodes) == {element[row["id"]] for row in old_nodes}
    positions = {row["node_id"]: (row["x"], row["y"]) for row in data["positions"] if row["line_id"] == version_id}
    for row in old_nodes:
        replayed = state.nodes[element[row["id"]]]
        assert (replayed.name, replayed.description, replayed.node_type_id) == (row["name"], row["description"], row["node_type_id"])
        assert positions[element[row["id"]]] == (row["x"], row["y"])
    assert set(positions) == set(state.nodes)
    old_connections = {(row["connection_type_id"], element[row["source_node_id"]], element[row["target_node_id"]]) for row in data["connections"] if row["version_id"] == version_id}
    assert {(c.connection_type_id, c.source_node_id, c.target_node_id) for c in state.connections.values()} == old_connections
    assert len(state.connections) == len(old_connections)


def test_upgrade_converts_every_version_without_losing_anything_and_downgrade_is_clean(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, base = _tenant(stack, database_url, "migration-lines")
    seeded = _seed(owner, base)
    model_id = UUID(seeded["org_model"])
    empty_model = owner.post(f"{base}/models", json={"name": "No baseline"}).json()["id"]
    stack.close()

    engine = create_engine(database_url)
    config = _config(database_url)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM model_versions WHERE model_id = :id"), {"id": empty_model})
        before = {
            table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            for table in ("metrics", "metric_values", "simulations", "nodes", "connections", "model_versions")
        }
    command.downgrade(config, "0060")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM model_lines")).scalar_one() == 0
        columns = {row[0] for row in connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name IN ('metrics', 'metric_values', 'simulations')"))}
        assert "line_id" not in columns and "version_id" in columns
    command.upgrade(config, "0061")
    try:
        data = _load(engine)
        with engine.connect() as connection:
            after = {table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in before}
            unmapped = connection.execute(text("SELECT (SELECT count(*) FROM metrics WHERE line_id IS DISTINCT FROM version_id) + (SELECT count(*) FROM metric_values WHERE line_id IS DISTINCT FROM version_id) + (SELECT count(*) FROM simulations WHERE line_id IS DISTINCT FROM version_id)")).scalar_one()
        assert after == before and unmapped == 0  # nothing lost; old tables intact; line_id = version_id

        lines = {row["id"]: row for row in data["lines"]}
        versions = {row["id"]: row for row in data["versions"]}
        kept = [version for version in versions.values() if version["model_id"] == model_id]
        assert len(kept) == 6
        for version in kept:  # each version became a line of the same id and name
            line = lines[version["id"]]
            assert line["kind"] == ("base" if version["is_baseline"] else "scenario") and line["name"] == version["name"]
        assert sum(1 for row in data["lines"] if row["kind"] == "base" and row["model_id"] == model_id) == 1
        for version in kept:
            _assert_replay_equals_old_graph(data, version["id"], model_id)

        events_of = lambda line_id: [row for row in data["events"] if row["line_id"] == line_id]  # noqa: E731
        baseline_line = UUID(seeded["baseline"])
        initial = events_of(baseline_line)
        assert [(row["title"]) for row in initial] == ["Initial situation"]
        model_day = None
        with engine.connect() as connection:
            model_day = connection.execute(text("SELECT (m.created_at AT TIME ZONE o.time_zone)::date FROM models m JOIN organizations o ON o.id = m.organization_id WHERE m.id = :id"), {"id": model_id}).scalar_one()
        assert initial[0]["occurred_on"] == model_day
        growth, deeper = UUID(seeded["growth"]), UUID(seeded["deeper"])
        assert (lines[growth]["parent_line_id"], lines[growth]["branch_event_id"]) == (baseline_line, initial[0]["id"])
        assert len(events_of(growth)) == 1 and events_of(growth)[0]["occurred_on"] >= initial[0]["occurred_on"]
        # A fork of a fork branches from its base fork's last event.
        assert (lines[deeper]["parent_line_id"], lines[deeper]["branch_event_id"]) == (growth, events_of(growth)[0]["id"])
        # No difference, no event; the fork below it branches where it branches.
        unchanged, below = UUID(seeded["unchanged"]), UUID(seeded["below_unchanged"])
        assert events_of(unchanged) == [] and events_of(below) == []
        assert (lines[below]["parent_line_id"], lines[below]["branch_event_id"]) == (baseline_line, initial[0]["id"])
        # The baseline's later node is something the forks lack: their events remove it.
        pruned_ops = [row["op"] for row in data["changes"] if row["event_id"] == events_of(UUID(seeded["pruned"]))[0]["id"]]
        assert pruned_ops == ["remove_node", "remove_node"]  # Onboarding (its connection goes with it) and Late
        # A Model with no baseline version still gets a Base line (empty initial situation).
        empty_lines = [row for row in data["lines"] if row["model_id"] == UUID(empty_model)]
        assert [row["kind"] for row in empty_lines] == ["base"]
        empty_events = events_of(empty_lines[0]["id"])
        assert [row["title"] for row in empty_events] == ["Initial situation"]
        assert not [row for row in data["changes"] if row["event_id"] == empty_events[0]["id"]]
        # Scenario events are never dated before the branch event.
        dates = {row["id"]: row["occurred_on"] for row in data["events"]}
        for line in data["lines"]:
            if line["kind"] == "scenario":
                assert all(row["occurred_on"] >= dates[line["branch_event_id"]] for row in events_of(line["id"]))

        command.downgrade(config, "0060")
        with engine.connect() as connection:
            for table in ("model_lines", "timeline_events", "event_changes", "node_positions"):
                assert connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
            assert {table: connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in before} == before
    finally:
        command.upgrade(config, "head")
        engine.dispose()


def test_a_new_model_has_a_base_line_with_an_empty_initial_situation(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, base = _tenant(stack, database_url, "migration-new-model")
    created = owner.post(f"{base}/models", json={"name": "Fresh"})
    assert created.status_code == 201
    model_id = UUID(created.json()["id"])
    baseline = UUID(_graph(owner, base, str(model_id))["version"]["id"])
    engine = create_engine(database_url)
    with engine.connect() as connection:
        zone = connection.execute(text("SELECT time_zone FROM organizations WHERE id = :id"), {"id": organization_id}).scalar_one()
        lines = connection.execute(text("SELECT id, kind, parent_line_id, name FROM model_lines WHERE model_id = :id"), {"id": model_id}).all()
        events = connection.execute(text("SELECT id, line_id, occurred_on, title FROM timeline_events WHERE model_id = :id"), {"id": model_id}).all()
        changes = connection.execute(text("SELECT count(*) FROM event_changes WHERE event_id = :id"), {"id": events[0].id}).scalar_one()
    engine.dispose()
    assert [(row.id, row.kind, row.parent_line_id, row.name) for row in lines] == [(baseline, "base", None, "Baseline")]
    assert [(row.line_id, row.title) for row in events] == [(baseline, "Initial situation")] and changes == 0
    assert abs((events[0].occurred_on - datetime.now(ZoneInfo(zone)).date()).days) <= 1
    # Deleting the Model removes its lines and events with it.
    assert owner.delete(f"{base}/models/{model_id}", params={"expected_version": 1}).status_code == 204
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM model_lines WHERE model_id = :id"), {"id": model_id}).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM timeline_events WHERE model_id = :id"), {"id": model_id}).scalar_one() == 0
    engine.dispose()
