"""Migration 0061: versions, graphs, metrics and simulations become lines and changes (model-timeline ticket 02).

The Model, its metrics and a simulation are made through the application; the schema is then moved back to 0061 (0064
recreates the old tables, with a version for every line), the old graph tables are written directly (the routes that wrote
them are gone), the schema is moved back to 0060 and up to 0061 again, and the replayed state of every line is compared with the old graph.
"""
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.timeline.chain import ChangeRecord, LineRecord, state_after
from app.timeline.state import Edit, Metamodel
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


class OldGraph:
    """Writes the old ``nodes`` and ``connections`` tables directly: the routes that did it are gone since ticket 07, the migration must still convert what they left."""

    def __init__(self, engine, organization_id: str, model_id: str) -> None:
        self.engine, self.org, self.model = engine, organization_id, model_id

    def run(self, sql: str, **params):
        with self.engine.begin() as connection:
            return connection.execute(text(sql), params)

    def node(self, version_id, type_id, name, description=None, x=0, y=0, origin=None) -> dict:
        node_id = uuid4()
        self.run(
            "INSERT INTO nodes (id, organization_id, model_id, version_id, origin_node_id, node_type_id, name, description, x, y) VALUES (:id, :org, :model, :version, :origin, :type, :name, :description, :x, :y)",
            id=node_id, org=self.org, model=self.model, version=version_id, origin=origin, type=type_id, name=name, description=description, x=x, y=y,
        )
        return {"id": node_id, "name": name}

    def connection(self, version_id, type_id, source, target) -> UUID:
        connection_id = uuid4()
        self.run("INSERT INTO connections (id, organization_id, model_id, version_id, connection_type_id, source_node_id, target_node_id) VALUES (:id, :org, :model, :version, :type, :source, :target)", id=connection_id, org=self.org, model=self.model, version=version_id, type=type_id, source=source, target=target)
        return connection_id

    def version(self, name, base_version) -> UUID:
        version_id = uuid4()
        self.run("INSERT INTO model_versions (id, organization_id, model_id, name, is_baseline, base_version_id) VALUES (:id, :org, :model, :name, false, :base)", id=version_id, org=self.org, model=self.model, name=name, base=base_version)
        return version_id

    def copy(self, base_version, fork_version) -> None:
        """What the old fork route did: copy the graph, every node remembering its origin."""
        mapping = {}
        with self.engine.connect() as connection:
            nodes = connection.execute(text("SELECT id, node_type_id, name, description, x, y FROM nodes WHERE version_id = :v ORDER BY created_at, id"), {"v": base_version}).mappings().all()
            links = connection.execute(text("SELECT connection_type_id, source_node_id, target_node_id FROM connections WHERE version_id = :v"), {"v": base_version}).mappings().all()
        for row in nodes:
            mapping[row["id"]] = self.node(fork_version, row["node_type_id"], row["name"], row["description"], row["x"], row["y"], origin=row["id"])["id"]
        for row in links:
            self.connection(fork_version, row["connection_type_id"], mapping[row["source_node_id"]], mapping[row["target_node_id"]])

    def named(self, version_id, name) -> UUID:
        return self.run("SELECT id FROM nodes WHERE version_id = :v AND name = :n", v=version_id, n=name).scalar_one()


def _seed_application(owner, base) -> dict:
    """What the application writes today: a Model with metrics, values and a simulation on its Base line."""
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    types = _types(_graph(owner, base, model_id))
    baseline = _graph(owner, base, model_id)["line"]["id"]
    metrics = f"{path}/lines/{baseline}/metrics"
    revenue = owner.post(metrics, json={"key": "revenue", "name": "Revenue", "unit": "EUR"}).json()
    owner.post(metrics, json={"key": "double", "name": "Double", "formula": "revenue * 2"})
    _values(owner, metrics, revenue["id"], [(f"2025-{m:02d}-01", 100 + m) for m in range(1, 13)])
    assert owner.post(f"{path}/lines/{baseline}/simulations", json={"name": "Base run", "method": "linear", "horizon_months": 3}).status_code == 201
    return {"org_model": model_id, "baseline": baseline, "types": types, "revenue": revenue["id"]}


def _seed_old(engine, organization_id, seeded) -> dict:
    """The old tables as the version routes left them (the schema is at 0061): a graph, forks of every shape and a metric of a fork."""
    model_id, baseline, types = seeded["org_model"], seeded["baseline"], seeded["types"]
    old = OldGraph(engine, organization_id, model_id)
    app = old.node(baseline, types["product"], "App", description="The product", x=10, y=20)
    journey = old.node(baseline, types["journey"], "Onboarding", x=30, y=40)
    terms = old.node(baseline, types["contract"], "Terms")
    old.connection(baseline, types["c:features_in"], app["id"], journey["id"])
    old.connection(baseline, types["c:is_composed_of"], app["id"], terms["id"])
    old.run("UPDATE metrics SET node_id = :node WHERE id = :id", node=app["id"], id=seeded["revenue"])  # tie the metric the way the old routes did

    def fork(name, base_version=None):
        created = old.version(name, base_version or baseline)
        old.copy(base_version or baseline, created)
        return str(created)

    # Growth: rename, move, drop one connection, add a node; it has a fork of its own.
    growth = fork("Growth")
    old.run("UPDATE nodes SET name = 'App 2', description = NULL, x = 111, y = 222 WHERE id = :id", id=old.named(growth, "App"))
    old.run("DELETE FROM connections WHERE version_id = :v AND connection_type_id = :t", v=growth, t=types["c:is_composed_of"])
    old.node(growth, types["product"], "Extra", x=5, y=6)
    deeper = fork("Growth deeper", growth)
    old.run("DELETE FROM nodes WHERE id = :id", id=old.named(deeper, "Onboarding"))
    added = old.node(deeper, types["journey"], "Checkout")
    old.connection(deeper, types["c:features_in"], old.named(deeper, "Extra"), added["id"])
    # Dropping a node takes its connections with it.
    pruned = fork("Pruned")
    old.run("DELETE FROM nodes WHERE id = :id", id=old.named(pruned, "Onboarding"))
    # The baseline moves on after the forks above were made: they lack its new node, so their changes remove it.
    old.node(baseline, types["person"], "Late")
    # Same as the baseline: no change of its own; a fork of it branches where it branches.
    unchanged = fork("Unchanged")
    below_unchanged = fork("Below unchanged", unchanged)
    old.run("INSERT INTO metrics (id, organization_id, model_id, version_id, key, name) VALUES (:id, :org, :model, :version, 'own', 'Own')", id=uuid4(), org=organization_id, model=model_id, version=below_unchanged)
    return {"org_model": model_id, "baseline": baseline, "growth": growth, "deeper": deeper, "unchanged": unchanged, "below_unchanged": below_unchanged, "pruned": pruned}


def _load(engine):
    with engine.connect() as connection:
        rows = lambda sql: [dict(row._mapping) for row in connection.execute(text(sql))]  # noqa: E731
        return {
            "versions": rows("SELECT * FROM model_versions"),
            "nodes": rows("SELECT * FROM nodes"),
            "connections": rows("SELECT * FROM connections"),
            "lines": rows("SELECT * FROM model_lines"),
            "changes": rows("SELECT * FROM timeline_events ORDER BY occurred_on, seq"),
            "edits": rows("SELECT * FROM event_changes ORDER BY event_id, position"),
            "positions": rows("SELECT * FROM node_positions"),
            "node_types": rows("SELECT id, model_id FROM node_types"),
            "connection_types": rows("SELECT id, model_id FROM connection_types"),
            "allowed": rows("SELECT * FROM allowed_connections"),
        }


def _engine_inputs(data, model_id):
    lines = {row["id"]: LineRecord(row["id"], row["parent_line_id"], row["branch_event_id"]) for row in data["lines"] if row["model_id"] == model_id}
    edits: dict = {}
    for row in data["edits"]:
        edits.setdefault(row["event_id"], []).append(Edit(row["op"], row["element_id"], row["payload"]))
    changes: dict = {}
    for row in data["changes"]:
        if row["model_id"] == model_id:
            changes.setdefault(row["line_id"], []).append(ChangeRecord(row["id"], row["line_id"], row["occurred_on"], row["seq"], row["title"], tuple(edits.get(row["id"], ()))))
    metamodel = Metamodel(
        frozenset(row["id"] for row in data["node_types"] if row["model_id"] == model_id),
        frozenset(row["id"] for row in data["connection_types"] if row["model_id"] == model_id),
        frozenset((row["connection_type_id"], row["source_node_type_id"], row["target_node_type_id"]) for row in data["allowed"] if row["model_id"] == model_id),
    )
    return lines, changes, metamodel


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
    lines, changes, metamodel = _engine_inputs(data, model_id)
    state = state_after(lines, changes, metamodel, version_id)
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
    engine = create_engine(database_url)
    application_seed = _seed_application(owner, base)
    empty_model = owner.post(f"{base}/models", json={"name": "No baseline"}).json()["id"]
    stack.close()

    config = _config(database_url)
    try:
        command.downgrade(config, "0061")  # 0064 gives the old tables back, with a version for every line
        seeded = _seed_old(engine, organization_id, application_seed)
        model_id = UUID(seeded["org_model"])
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

        changes_of = lambda line_id: [row for row in data["changes"] if row["line_id"] == line_id]  # noqa: E731
        baseline_line = UUID(seeded["baseline"])
        initial = changes_of(baseline_line)
        assert [(row["title"]) for row in initial] == ["Initial situation"]
        model_day = None
        with engine.connect() as connection:
            model_day = connection.execute(text("SELECT (m.created_at AT TIME ZONE o.time_zone)::date FROM models m JOIN organizations o ON o.id = m.organization_id WHERE m.id = :id"), {"id": model_id}).scalar_one()
        assert initial[0]["occurred_on"] == model_day
        growth, deeper = UUID(seeded["growth"]), UUID(seeded["deeper"])
        assert (lines[growth]["parent_line_id"], lines[growth]["branch_event_id"]) == (baseline_line, initial[0]["id"])
        assert len(changes_of(growth)) == 1 and changes_of(growth)[0]["occurred_on"] >= initial[0]["occurred_on"]
        # A fork of a fork branches from its base fork's last change.
        assert (lines[deeper]["parent_line_id"], lines[deeper]["branch_event_id"]) == (growth, changes_of(growth)[0]["id"])
        # No difference, no change; the fork below it branches where it branches.
        unchanged, below = UUID(seeded["unchanged"]), UUID(seeded["below_unchanged"])
        assert changes_of(unchanged) == [] and changes_of(below) == []
        assert (lines[below]["parent_line_id"], lines[below]["branch_event_id"]) == (baseline_line, initial[0]["id"])
        # The baseline's later node is something the forks lack: their changes remove it.
        pruned_ops = [row["op"] for row in data["edits"] if row["event_id"] == changes_of(UUID(seeded["pruned"]))[0]["id"]]
        assert pruned_ops == ["remove_node", "remove_node"]  # Onboarding (its connection goes with it) and Late
        # A Model with no baseline version still gets a Base line (empty initial situation).
        empty_lines = [row for row in data["lines"] if row["model_id"] == UUID(empty_model)]
        assert [row["kind"] for row in empty_lines] == ["base"]
        empty_changes = changes_of(empty_lines[0]["id"])
        assert [row["title"] for row in empty_changes] == ["Initial situation"]
        assert not [row for row in data["edits"] if row["event_id"] == empty_changes[0]["id"]]
        # Scenario changes are never dated before the branch change.
        dates = {row["id"]: row["occurred_on"] for row in data["changes"]}
        for line in data["lines"]:
            if line["kind"] == "scenario":
                assert all(row["occurred_on"] >= dates[line["branch_event_id"]] for row in changes_of(line["id"]))

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
    baseline = UUID(_graph(owner, base, str(model_id))["line"]["id"])
    engine = create_engine(database_url)
    with engine.connect() as connection:
        zone = connection.execute(text("SELECT time_zone FROM organizations WHERE id = :id"), {"id": organization_id}).scalar_one()
        lines = connection.execute(text("SELECT id, kind, parent_line_id, name FROM model_lines WHERE model_id = :id"), {"id": model_id}).all()
        changes = connection.execute(text("SELECT id, line_id, occurred_on, title FROM timeline_changes WHERE model_id = :id"), {"id": model_id}).all()
        edits = connection.execute(text("SELECT count(*) FROM change_edits WHERE change_id = :id"), {"id": changes[0].id}).scalar_one()
    engine.dispose()
    assert [(row.id, row.kind, row.parent_line_id, row.name) for row in lines] == [(baseline, "base", None, "Baseline")]
    assert [(row.line_id, row.title) for row in changes] == [(baseline, "Initial situation")] and edits == 0
    assert abs((changes[0].occurred_on - datetime.now(ZoneInfo(zone)).date()).days) <= 1
    # Deleting the Model removes its lines and changes with it.
    assert owner.delete(f"{base}/models/{model_id}", params={"expected_version": 1}).status_code == 204
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM model_lines WHERE model_id = :id"), {"id": model_id}).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM timeline_changes WHERE model_id = :id"), {"id": model_id}).scalar_one() == 0
    engine.dispose()


def test_migration_0064_drops_the_version_tables_and_downgrade_recreates_them_from_the_lines(database_url: str, stack: ExitStack) -> None:
    _, owner, organization_id, base = _tenant(stack, database_url, "migration-0064")
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    path = f"{base}/models/{model_id}"
    types = _types(_graph(owner, base, model_id))
    baseline = _graph(owner, base, model_id)["line"]["id"]
    change = owner.get(f"{path}/lines/{baseline}/changes").json()[-1]["id"]
    owner.post(f"{path}/changes/{change}/nodes", json={"node_type_id": types["product"], "name": "App"})
    scenario = owner.post(f"{path}/lines", json={"name": "What if", "description": "Later", "branch_change_id": change}).json()["id"]
    owner.post(f"{path}/lines/{baseline}/metrics", json={"key": "revenue", "name": "Revenue"})
    stack.close()
    engine = create_engine(database_url)
    config = _config(database_url)
    tables = lambda: {row[0] for row in engine.connect().execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))}  # noqa: E731
    try:
        assert not tables() & {"model_versions", "nodes", "connections"}  # gone at head
        command.downgrade(config, "0063")
        assert {"model_versions", "nodes", "connections"} <= tables()
        with engine.connect() as connection:
            versions = {str(row.id): row for row in connection.execute(text("SELECT * FROM model_versions WHERE model_id = :id"), {"id": model_id})}
            assert set(versions) == {baseline, scenario}  # one version per line, with the line's id
            assert versions[baseline].is_baseline and versions[baseline].base_version_id is None and versions[baseline].name == "Baseline"
            assert not versions[scenario].is_baseline and str(versions[scenario].base_version_id) == baseline and versions[scenario].description == "Later"
            assert connection.execute(text("SELECT count(*) FROM nodes WHERE model_id = :id"), {"id": model_id}).scalar_one() == 0  # the timeline is the source: no graph is rebuilt
            assert connection.execute(text("SELECT count(*) FROM connections WHERE model_id = :id"), {"id": model_id}).scalar_one() == 0
            policies = {row[0] for row in connection.execute(text("SELECT tablename FROM pg_policies WHERE tablename IN ('nodes', 'connections', 'model_versions')"))}
            forced = connection.execute(text("SELECT count(*) FROM pg_class WHERE relname IN ('nodes', 'connections', 'model_versions') AND relforcerowsecurity")).scalar_one()
        assert policies == {"nodes", "connections", "model_versions"} and forced == 3
        command.downgrade(config, "0061")  # the older migrations still find their versions and keep the metrics
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM metrics WHERE model_id = :id AND version_id = :line"), {"id": model_id, "line": baseline}).scalar_one() == 1
    finally:
        command.upgrade(config, "head")
        engine.dispose()
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert not {row[0] for row in connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))} & {"model_versions", "nodes", "connections"}
        assert connection.execute(text("SELECT count(*) FROM metrics WHERE model_id = :id AND line_id = :line"), {"id": model_id, "line": baseline}).scalar_one() == 1
    engine.dispose()
