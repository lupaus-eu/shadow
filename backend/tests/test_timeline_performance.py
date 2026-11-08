"""Timing of the state read, the change list and a validated write at the target size (model-timeline ticket 10).

2000 changes and 500 nodes on the Base line, four Scenarios (one of them branching from another) with a few dozen changes each.
Excluded from the normal run; run it with `pytest -m perf -s` (the timings are printed).
"""
import random
import time
from contextlib import ExitStack
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.database import RequestContext, transaction_session
from app.models import ChangeEdit, ModelLine, TimelineChange
from test_timeline_changes import World

pytestmark = pytest.mark.perf

CHANGES, NODES, REMOVALS = 2000, 500, 60
STATE_LIMIT, CHANGES_LIMIT, WRITE_LIMIT = 2.0, 2.0, 5.0


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _build_base_edits(types: dict[str, str], rng: random.Random):
    """Yield (title, edits) for changes 2..CHANGES: add nodes (journeys joined to a product), then renames, re-routes and removals."""
    products: list[str] = []
    nodes: dict[str, str] = {}  # id -> kind
    connections: dict[str, tuple[str, str]] = {}  # id -> (product, journey)
    additions = NODES + REMOVALS
    removal_every = (CHANGES - 1 - additions) // REMOVALS
    for index in range(CHANGES - 1):
        edits: list[dict] = []
        if index < additions:
            node = str(uuid4())
            if index % 2 == 0 or not products:
                nodes[node] = "product"
                products.append(node)
                edits.append({"op": "add_node", "element_id": node, "payload": {"node_type_id": types["product"], "name": f"Product {index}", "x": index % 40 * 30, "y": index // 40 * 30}})
            else:
                nodes[node] = "journey"
                edits.append({"op": "add_node", "element_id": node, "payload": {"node_type_id": types["journey"], "name": f"Journey {index}", "x": index % 40 * 30, "y": index // 40 * 30}})
                source, edge = rng.choice(products), str(uuid4())
                connections[edge] = (source, node)
                edits.append({"op": "add_connection", "element_id": edge, "payload": {"connection_type_id": types["c:features_in"], "source_node_id": source, "target_node_id": node}})
            title = f"Add {index}"
        elif (index - additions) % removal_every == 0 and len(nodes) > NODES:
            victim = rng.choice(sorted(nodes))
            edits.append({"op": "remove_node", "element_id": victim, "payload": {}})
            nodes.pop(victim)
            products = [item for item in products if item != victim]
            for edge in [edge for edge, ends in connections.items() if victim in ends]:
                del connections[edge]
            title = f"Remove {index}"
        elif index % 2 == 0 and connections:
            edge = rng.choice(sorted(connections))
            _, target = connections[edge]
            candidates = [item for item in products if (item, target) not in connections.values()]
            source = rng.choice(candidates)
            connections[edge] = (source, target)
            edits.append({"op": "reroute_connection", "element_id": edge, "payload": {"source_node_id": source}})
            title = f"Re-route {index}"
        else:
            node = rng.choice(sorted(nodes))
            edits.append({"op": "update_node", "element_id": node, "payload": {"name": f"Renamed {index}"}})
            title = f"Rename {index}"
        yield title, edits
    assert len(nodes) == NODES


def _insert_change(session, org: UUID, model: UUID, line: UUID, day: date, title: str, edits: list[dict]) -> UUID:
    change = TimelineChange(id=uuid4(), organization_id=org, model_id=model, line_id=line, occurred_on=day, title=title)
    session.add(change)
    session.flush()
    session.add_all([ChangeEdit(id=uuid4(), organization_id=org, change_id=change.id, position=position, op=item["op"], element_id=UUID(item["element_id"]), payload=item["payload"]) for position, item in enumerate(edits)])
    return change.id


def _scenario(session, org: UUID, model: UUID, name: str, parent: UUID, branch: UUID, since: date, changes: int, types: dict[str, str]) -> tuple[UUID, list[UUID]]:
    line = ModelLine(id=uuid4(), organization_id=org, model_id=model, name=name, kind="scenario", parent_line_id=parent, branch_change_id=branch)
    session.add(line)
    session.flush()
    ids = []
    for index in range(changes):
        node = uuid4()
        ids.append(_insert_change(session, org, model, line.id, since + timedelta(days=index), f"{name} {index}", [{"op": "add_node", "element_id": str(node), "payload": {"node_type_id": types["product"], "name": f"{name} idea {index}", "x": index * 20, "y": 900}}]))
    return line.id, ids


def _best_of(call, runs: int = 3) -> tuple[float, list[float]]:
    timings = []
    for _ in range(runs):
        started = time.perf_counter()
        call()
        timings.append(time.perf_counter() - started)
    return max(timings), timings


def test_state_changes_and_a_validated_write_stay_within_the_limits(database_url: str, stack: ExitStack) -> None:
    world = World(stack, database_url, "tl-perf")
    org, model, base = UUID(world.org), UUID(world.model), UUID(world.line)
    rng = random.Random(2000)
    first_day = date(2024, 1, 1)
    with transaction_session(world.factory, RequestContext(organization_id=org)) as session:
        session.execute(text("UPDATE timeline_changes SET occurred_on = :day WHERE line_id = :line"), {"day": first_day - timedelta(days=1), "line": base})
        change_ids: list[tuple[UUID, str]] = []
        for index, (title, edits) in enumerate(_build_base_edits(world.types, rng)):
            change_ids.append((_insert_change(session, org, model, base, first_day + timedelta(days=index // 4), title, edits), title))
        middle = next(change for change, title in change_ids[1000:] if title.startswith("Rename"))
        later = next(change for change, title in change_ids[1500:] if title.startswith("Rename"))
        branch_date = session.scalar(select(TimelineChange.occurred_on).where(TimelineChange.id == middle))
        late_date = session.scalar(select(TimelineChange.occurred_on).where(TimelineChange.id == later))
        scenarios = [_scenario(session, org, model, f"Scenario {number}", base, middle, branch_date, 30, world.types) for number in range(3)]
        _scenario(session, org, model, "Scenario late", base, later, late_date, 20, world.types)
        _scenario(session, org, model, "Scenario child", scenarios[0][0], scenarios[0][1][9], branch_date + timedelta(days=9), 20, world.types)

    assert len(world.changes()) == CHANGES
    state_path = f"{world.path}/lines/{world.line}"
    state = world.state()
    assert len(state["nodes"]) == NODES and len(state["connections"]) > 200
    state_worst, state_times = _best_of(lambda: world.owner.get(f"{state_path}/state").raise_for_status())
    changes_worst, changes_times = _best_of(lambda: world.owner.get(f"{state_path}/changes").raise_for_status())

    detail = world.owner.get(f"{world.path}/changes/{middle}").json()
    node = detail["edits"][0]["element_id"]
    versions = [detail["version"]]
    write_times = []
    for round_ in range(3):
        started = time.perf_counter()
        response = world.owner.patch(f"{world.path}/changes/{middle}", json={"expected_version": versions[-1], "title": f"Corrected {round_}", "edits": [{"op": "update_node", "element_id": node, "payload": {"name": f"Corrected name {round_}"}}]})
        write_times.append(time.perf_counter() - started)
        assert response.status_code == 200, response.text
        versions.append(response.json()["version"])
    write_worst = max(write_times)

    def fmt(values: list[float]) -> str:
        return ", ".join(f"{value:.3f}" for value in values)

    print(f"\nPERF model with {CHANGES} changes, {len(state['nodes'])} nodes, {len(state['connections'])} connections, 5 Scenarios")
    print(f"PERF state (s): {fmt(state_times)}")
    print(f"PERF changes (s): {fmt(changes_times)}")
    print(f"PERF validated write, branch change with 4 Scenarios (s): {fmt(write_times)}")
    assert state_worst < STATE_LIMIT, state_times
    assert changes_worst < CHANGES_LIMIT, changes_times
    assert write_worst < WRITE_LIMIT, write_times
