"""Metrics, simulations and analysis belong to a line (model-timeline ticket 04): scoping, the old fork and delete routes, and migration 0062."""
from contextlib import ExitStack
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from test_metrics import _values
from test_models_graph import _graph, _tenant

BACKEND = Path(__file__).resolve().parents[1]
MONTHS = [(f"2025-{month:02d}-01", 100 + month) for month in range(1, 13)]


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _model(stack, database_url, subject):
    _, owner, organization_id, base = _tenant(stack, database_url, subject)
    model_id = owner.post(f"{base}/models", json={"name": "Twin"}).json()["id"]
    return owner, UUID(organization_id), base, model_id, _graph(owner, base, model_id)["version"]["id"]


def test_the_old_fork_route_creates_a_scenario_line_and_copies_metrics_line_wise(database_url: str, stack: ExitStack) -> None:
    owner, _, base, model_id, baseline = _model(stack, database_url, "lines-fork")
    path = f"{base}/models/{model_id}"
    lines = lambda: owner.get(f"{path}/lines").json()  # noqa: E731
    base_events = owner.get(f"{path}/lines/{baseline}/events").json()
    metrics = f"{path}/lines/{baseline}/metrics"
    revenue = owner.post(metrics, json={"key": "revenue", "name": "Revenue"}).json()
    owner.post(metrics, json={"key": "double", "name": "Double", "formula": "revenue * 2"})
    assert _values(owner, metrics, revenue["id"], MONTHS).status_code == 200
    fork = owner.post(f"{path}/versions", json={"name": "Scenario", "description": "What if"}).json()
    scenario = next(line for line in lines() if line["id"] == fork["id"])  # a line with the id of the version
    assert scenario["kind"] == "scenario" and scenario["parent_line_id"] == baseline and scenario["name"] == "Scenario"
    assert scenario["branch_event_id"] == base_events[-1]["id"]  # the Base line's last event; none was added
    copies = {m["key"]: m for m in owner.get(f"{path}/lines/{fork['id']}/metrics").json()}
    assert set(copies) == {"revenue", "double"} and copies["revenue"]["values"] == 12
    # Scoped to the line: same keys in both lines, edits and formulas stay inside one.
    assert _values(owner, f"{path}/lines/{fork['id']}/metrics", copies["revenue"]["id"], [("2025-01-01", 1)]).status_code == 200
    assert owner.get(f"{metrics}/{revenue['id']}/series").json()["points"][0]["value"] == 101
    assert owner.get(f"{path}/lines/{fork['id']}/metrics/{copies['double']['id']}/series").json()["points"][0]["value"] == 2
    assert owner.get(f"{metrics}/{copies['revenue']['id']}/series").status_code == 404  # another line's metric
    assert owner.post(f"{path}/lines/{fork['id']}/metrics", json={"key": "revenue", "name": "Again"}).status_code == 409
    assert owner.delete(f"{path}/lines/{fork['id']}/metrics/{copies['revenue']['id']}", params={"expected_version": 2}).status_code == 409  # read by the formula
    # A simulation runs on one line and reads that line's metrics.
    run = owner.post(f"{path}/lines/{fork['id']}/simulations", json={"name": "Plan", "horizon_months": 3})
    assert run.status_code == 201 and run.json()["simulation"]["line_id"] == fork["id"]
    assert owner.get(f"{path}/lines/{baseline}/simulations").json() == []
    assert owner.get(f"{path}/lines/{baseline}/simulations/{run.json()['simulation']['id']}").status_code == 404
    # Rename follows; the base line keeps its events (no extra Initial situation event when one exists).
    assert owner.patch(f"{path}/versions/{fork['id']}", json={"name": "Renamed", "description": None, "expected_version": 1}).status_code == 200
    assert next(line for line in lines() if line["id"] == fork["id"])["name"] == "Renamed"
    assert len(owner.get(f"{path}/lines/{baseline}/events").json()) == len(base_events)
    # Deleting the version deletes its line, metrics and simulations.
    assert owner.delete(f"{path}/versions/{fork['id']}", params={"expected_version": 2}).status_code == 204
    assert [line["id"] for line in lines()] == [baseline]
    assert owner.get(f"{path}/lines/{fork['id']}/metrics").status_code == 404
    engine = create_engine(database_url)
    with engine.connect() as connection:
        left = connection.execute(text("SELECT (SELECT count(*) FROM metrics WHERE line_id = :id) + (SELECT count(*) FROM metric_values WHERE line_id = :id) + (SELECT count(*) FROM simulations WHERE line_id = :id)"), {"id": UUID(fork["id"])}).scalar_one()
    engine.dispose()
    assert left == 0


def test_a_base_line_without_events_gets_an_initial_situation_when_forked(database_url: str, stack: ExitStack) -> None:
    owner, _, base, model_id, baseline = _model(stack, database_url, "lines-fork-empty")
    path = f"{base}/models/{model_id}"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM timeline_events WHERE line_id = :id"), {"id": UUID(baseline)})
    engine.dispose()
    assert owner.get(f"{path}/lines/{baseline}/events").json() == []
    fork = owner.post(f"{path}/versions", json={"name": "Scenario"})
    assert fork.status_code == 201
    events = owner.get(f"{path}/lines/{baseline}/events").json()
    assert [(event["title"], event["change_count"]) for event in events] == [("Initial situation", 0)]
    scenario = next(line for line in owner.get(f"{path}/lines").json() if line["id"] == fork.json()["id"])
    assert scenario["branch_event_id"] == events[0]["id"]


def test_unknown_lines_answer_404_and_other_models_lines_are_not_reachable(database_url: str, stack: ExitStack) -> None:
    owner, _, base, model_id, baseline = _model(stack, database_url, "lines-404")
    other = owner.post(f"{base}/models", json={"name": "Other"}).json()["id"]
    assert owner.get(f"{base}/models/{model_id}/lines/{uuid4()}/metrics").status_code == 404
    assert owner.get(f"{base}/models/{other}/lines/{baseline}/metrics").status_code == 404
    assert owner.get(f"{base}/models/{other}/lines/{baseline}/simulations").status_code == 404
    assert owner.get(f"{base}/models/{other}/lines/{baseline}/metrics/export").status_code == 404


def test_metrics_can_point_at_a_node_of_the_line(database_url: str, stack: ExitStack) -> None:
    owner, _, base, model_id, baseline = _model(stack, database_url, "lines-node")
    path = f"{base}/models/{model_id}"
    types = {item["key"]: item["id"] for item in _graph(owner, base, model_id)["node_types"]}
    node = owner.post(f"{path}/nodes", json={"node_type_id": types["product"], "name": "App"}).json()
    created = owner.post(f"{path}/lines/{baseline}/metrics", json={"key": "users", "name": "Users", "node_id": node["id"]})
    assert created.status_code == 201 and created.json()["node_id"] == node["id"]
    assert owner.post(f"{path}/lines/{baseline}/metrics", json={"key": "ghost", "name": "Ghost", "node_id": str(uuid4())}).status_code == 422


def _config(database_url: str) -> Config:
    config = Config(BACKEND / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_migration_0062_makes_line_id_required_and_drops_version_id(database_url: str, stack: ExitStack) -> None:
    owner, organization_id, base, model_id, baseline = _model(stack, database_url, "lines-migration")
    path = f"{base}/models/{model_id}"
    kept = owner.post(f"{path}/lines/{baseline}/metrics", json={"key": "kept", "name": "Kept"}).json()
    assert _values(owner, f"{path}/lines/{baseline}/metrics", kept["id"], MONTHS[:2]).status_code == 200
    fork = owner.post(f"{path}/versions", json={"name": "Scenario"}).json()["id"]
    stack.close()
    engine = create_engine(database_url)
    config = _config(database_url)
    model, orphan, legacy, orphan_metric = UUID(model_id), uuid4(), uuid4(), uuid4()
    try:
        command.downgrade(config, "0061")
        with engine.begin() as connection:
            columns = {row[0] for row in connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'metrics'"))}
            assert {"line_id", "version_id"} <= columns
            ids = {"org": organization_id, "model": model}
            # Written by the old routes after 0061: no line_id. One on the baseline (has a line), one on a version without a line.
            connection.execute(text("INSERT INTO metrics (id, organization_id, model_id, version_id, key, name) VALUES (:id, :org, :model, :version, 'legacy', 'Legacy')"), {**ids, "id": legacy, "version": UUID(baseline)})
            connection.execute(text("INSERT INTO metric_values (metric_id, period, organization_id, version_id, value) VALUES (:id, '2025-01-01', :org, :version, 5)"), {"id": legacy, "org": organization_id, "version": UUID(baseline)})
            connection.execute(text("INSERT INTO model_versions (id, organization_id, model_id, name, is_baseline, base_version_id) VALUES (:id, :org, :model, 'Orphan', false, :base)"), {**ids, "id": orphan, "base": UUID(baseline)})
            connection.execute(text("INSERT INTO metrics (id, organization_id, model_id, version_id, key, name) VALUES (:id, :org, :model, :version, 'orphan', 'Orphan')"), {**ids, "id": orphan_metric, "version": orphan})
        command.upgrade(config, "0062")
        with engine.connect() as connection:
            columns = {row[0] for table in ("metrics", "metric_values", "simulations") for row in connection.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' AND column_name IN ('version_id', 'line_id')"))}
            assert columns == {"line_id"}
            nullable = connection.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name IN ('metrics', 'metric_values', 'simulations') AND column_name = 'line_id' AND is_nullable = 'YES'")).scalar_one()
            assert nullable == 0
            rows = {(row.key, row.line_id) for row in connection.execute(text("SELECT key, line_id FROM metrics WHERE model_id = :model"), {"model": model})}
            assert rows == {("kept", UUID(baseline)), ("kept", UUID(fork)), ("legacy", UUID(baseline))}  # a row of a version with a line is kept; the orphan's is gone
            assert connection.execute(text("SELECT count(*) FROM model_versions WHERE id = :id"), {"id": orphan}).scalar_one() == 0
            assert connection.execute(text("SELECT line_id FROM metric_values WHERE metric_id = :id"), {"id": legacy}).scalar_one() == UUID(baseline)
            assert connection.execute(text("SELECT count(*) FROM model_versions WHERE id = :id"), {"id": UUID(fork)}).scalar_one() == 1
        command.downgrade(config, "0061")  # restores version_id from line_id
        with engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM metrics WHERE version_id IS DISTINCT FROM line_id")).scalar_one() == 0
    finally:
        command.upgrade(config, "head")
        engine.dispose()
