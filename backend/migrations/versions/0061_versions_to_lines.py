"""Convert Model versions to lines and events (ADR-0048); add ``line_id`` beside ``version_id``.

Per Model: the baseline version becomes the Base line, whose graph becomes one event "Initial situation"
(add changes) dated the Model's creation day in the Organization's time zone, with the node positions
copied into ``node_positions``. Each fork becomes a Scenario branching from its base's last event, with one
event holding the difference to its base (removed connections, removed nodes, added nodes, updated nodes,
added connections), dated the fork's creation day (never before the branch event). A fork with no
difference gets no event; a fork of such a fork then branches from the same event as its base. A Model
with no baseline version gets an empty Base line.

Identity rules (so replayed states can be compared with the old graphs):

* A line takes the id of the version it comes from (a Model without a baseline version gets a new id), so
  ``line_id = version_id`` for every converted row and new Models created by the application follow the
  same rule until ticket 04 drops ``version_id``.
* A baseline node or connection keeps its id as its element id. A fork node whose ``origin_node_id`` is a
  node of its base uses that node's element id; a fork connection whose (type, source, target) matches a
  connection of its base uses that connection's element id; everything else keeps its own id and is added
  by the fork's event. ``metrics.node_id`` is not touched (it still references the old ``nodes`` rows;
  ticket 08 remaps it through these rules before dropping ``nodes``).

``metrics``, ``metric_values`` and ``simulations`` gain a nullable ``line_id`` (backfilled from
``version_id``, indexed, with foreign keys to ``model_lines``). ``version_id``, ``nodes``, ``connections`` and
``model_versions`` stay: routes still use them until tickets 04 and 08. ``line_id`` is nullable because those
routes do not write it yet; ticket 04 makes it required and drops ``version_id``.

Downgrade drops the ``line_id`` columns and constraints and truncates ``node_positions``,
``event_changes``, ``timeline_events`` and ``model_lines``. Nothing wrote those tables before this
migration, and the old tables are intact, so no graph is rebuilt and none is lost; lines and events
recorded after this migration are lost on downgrade.

Revision ID: 0061
Revises: 0060
"""

import json
from collections import defaultdict
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

INITIAL_TITLE = "Initial situation"
SCENARIO_TITLE = "Scenario changes"
LINE_TABLES = ("metrics", "simulations")


def _node_payload(node) -> dict:
    payload = {"node_type_id": str(node["node_type_id"]), "name": node["name"], "x": node["x"], "y": node["y"]}
    if node["description"] is not None:
        payload["description"] = node["description"]
    return payload


def _insert_event(bind, model, line_id, day, title, created_at, changes) -> tuple:
    event_id = uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO timeline_events (id, organization_id, model_id, line_id, occurred_on, title, created_at, updated_at) "
            "VALUES (:id, :organization_id, :model_id, :line_id, :day, :title, :created_at, :created_at)"
        ),
        {"id": event_id, "organization_id": model["organization_id"], "model_id": model["id"], "line_id": line_id, "day": day, "title": title, "created_at": created_at},
    )
    if changes:
        bind.execute(
            sa.text(
                "INSERT INTO event_changes (id, organization_id, event_id, position, op, element_id, payload) "
                "VALUES (:id, :organization_id, :event_id, :position, :op, :element_id, CAST(:payload AS jsonb))"
            ),
            [
                {"id": uuid4(), "organization_id": model["organization_id"], "event_id": event_id, "position": position, "op": op_name, "element_id": element, "payload": json.dumps(payload)}
                for position, (op_name, element, payload) in enumerate(changes)
            ],
        )
    return event_id, day


def _insert_positions(bind, model, line_id, nodes) -> None:
    if nodes:
        bind.execute(
            sa.text("INSERT INTO node_positions (line_id, node_id, organization_id, model_id, x, y) VALUES (:line_id, :node_id, :organization_id, :model_id, :x, :y)"),
            [{"line_id": line_id, "node_id": eid, "organization_id": model["organization_id"], "model_id": model["id"], "x": node["x"], "y": node["y"]} for eid, node in nodes.items()],
        )


def _insert_line(bind, model, line_id, name, description, kind, parent, branch, created_at) -> None:
    bind.execute(
        sa.text(
            "INSERT INTO model_lines (id, organization_id, model_id, name, description, kind, parent_line_id, branch_event_id, created_at) "
            "VALUES (:id, :organization_id, :model_id, :name, :description, :kind, :parent, :branch, :created_at)"
        ),
        {"id": line_id, "organization_id": model["organization_id"], "model_id": model["id"], "name": name, "description": description, "kind": kind, "parent": parent, "branch": branch, "created_at": created_at},
    )


def _convert_data(bind) -> None:
    models = bind.execute(
        sa.text(
            "SELECT m.id, m.organization_id, m.created_at, (m.created_at AT TIME ZONE o.time_zone)::date AS day "
            "FROM models m JOIN organizations o ON o.id = m.organization_id ORDER BY m.created_at, m.id"
        )
    ).mappings().all()
    versions = defaultdict(list)
    for row in bind.execute(
        sa.text(
            "SELECT v.id, v.model_id, v.name, v.description, v.is_baseline, v.base_version_id, v.created_at, "
            "(v.created_at AT TIME ZONE o.time_zone)::date AS day "
            "FROM model_versions v JOIN organizations o ON o.id = v.organization_id ORDER BY v.created_at, v.id"
        )
    ).mappings():
        versions[row["model_id"]].append(row)
    nodes = defaultdict(list)
    for row in bind.execute(sa.text("SELECT id, version_id, origin_node_id, node_type_id, name, description, x, y FROM nodes ORDER BY created_at, id")).mappings():
        nodes[row["version_id"]].append(row)
    connections = defaultdict(list)
    for row in bind.execute(sa.text("SELECT id, version_id, connection_type_id, source_node_id, target_node_id FROM connections ORDER BY created_at, id")).mappings():
        connections[row["version_id"]].append(row)

    element_of: dict = {}  # old node id -> element id
    # Per converted version: its graph by element id.
    graph_nodes: dict = {}
    graph_connections: dict = {}
    last_event: dict = {}  # line id -> (event id, date) of its last event
    branch_of: dict = {}  # line id -> (parent line id, branch event id, branch date)

    for model in models:
        own = versions.get(model["id"], [])
        taken = {row["name"].lower() for row in own}
        baseline = next((row for row in own if row["is_baseline"]), None)
        base_id = baseline["id"] if baseline else uuid4()
        base_name = baseline["name"] if baseline else ("Baseline" if "baseline" not in taken else "Base line")
        _insert_line(bind, model, base_id, base_name, baseline["description"] if baseline else None, "base", None, None, model["created_at"])
        base_nodes = {row["id"]: row for row in nodes.get(base_id, [])}
        base_connections = {row["id"]: row for row in connections.get(base_id, [])}
        changes = [("add_node", eid, _node_payload(node)) for eid, node in base_nodes.items()]
        changes += [
            ("add_connection", eid, {"connection_type_id": str(row["connection_type_id"]), "source_node_id": str(row["source_node_id"]), "target_node_id": str(row["target_node_id"])})
            for eid, row in base_connections.items()
        ]
        last_event[base_id] = _insert_event(bind, model, base_id, model["day"], INITIAL_TITLE, model["created_at"], changes)
        for eid in base_nodes:
            element_of[eid] = eid
        graph_nodes[base_id] = base_nodes
        graph_connections[base_id] = {eid: (row["connection_type_id"], row["source_node_id"], row["target_node_id"]) for eid, row in base_connections.items()}
        _insert_positions(bind, model, base_id, base_nodes)

        pending = [row for row in own if not row["is_baseline"]]
        ids = {row["id"] for row in own}
        while pending:
            ready = next(
                (row for row in pending if (row["base_version_id"] if row["base_version_id"] in ids else base_id) in graph_nodes),
                None,
            )
            if ready is None:  # a cycle cannot happen (a fork is created after its base); fall back to the baseline
                ready = pending[0]
                base = base_id
            else:
                base = ready["base_version_id"] if ready["base_version_id"] in ids else base_id
            pending.remove(ready)
            line_id = ready["id"]
            base_state, base_links = graph_nodes[base], graph_connections[base]

            fork_nodes: dict = {}
            for node in nodes.get(line_id, []):
                origin = element_of.get(node["origin_node_id"]) if node["origin_node_id"] else None
                eid = origin if origin in base_state and origin not in fork_nodes else node["id"]
                element_of[node["id"]] = eid
                fork_nodes[eid] = node
            base_keys = {key: eid for eid, key in base_links.items()}
            fork_links: dict = {}
            for row in connections.get(line_id, []):
                key = (row["connection_type_id"], element_of[row["source_node_id"]], element_of[row["target_node_id"]])
                eid = base_keys.get(key)
                fork_links[eid if eid is not None and eid not in fork_links else row["id"]] = key

            removed_nodes = [eid for eid in base_state if eid not in fork_nodes]
            removed_links = [eid for eid, key in base_links.items() if eid not in fork_links and key[1] not in removed_nodes and key[2] not in removed_nodes]
            changes = [("remove_connection", eid, {}) for eid in removed_links]
            changes += [("remove_node", eid, {}) for eid in removed_nodes]
            changes += [("add_node", eid, _node_payload(node)) for eid, node in fork_nodes.items() if eid not in base_state]
            for eid, node in fork_nodes.items():
                before = base_state.get(eid)
                if before is not None:
                    payload = {name: (str(node[name]) if name == "node_type_id" else node[name]) for name in ("name", "description", "node_type_id") if node[name] != before[name]}
                    if payload:
                        changes.append(("update_node", eid, payload))
            changes += [
                ("add_connection", eid, {"connection_type_id": str(key[0]), "source_node_id": str(key[1]), "target_node_id": str(key[2])})
                for eid, key in fork_links.items()
                if eid not in base_links
            ]

            if last_event.get(base):
                parent, (branch_event, branch_day) = base, last_event[base]
            else:  # the base fork has no events: branch where it branches (its state is the same)
                parent, branch_event, branch_day = branch_of[base]
            day = max(ready["day"], branch_day)
            _insert_line(bind, model, line_id, ready["name"], ready["description"], "scenario", parent, branch_event, ready["created_at"])
            branch_of[line_id] = (parent, branch_event, branch_day)
            if changes:
                last_event[line_id] = _insert_event(bind, model, line_id, day, SCENARIO_TITLE, ready["created_at"], changes)
            graph_nodes[line_id] = fork_nodes
            graph_connections[line_id] = fork_links
            _insert_positions(bind, model, line_id, fork_nodes)


def upgrade() -> None:
    for table in (*LINE_TABLES, "metric_values"):
        op.add_column(table, sa.Column("line_id", sa.Uuid(), nullable=True))
    _convert_data(op.get_bind())
    for table in (*LINE_TABLES, "metric_values"):
        op.execute(f"UPDATE {table} SET line_id = version_id")
        op.create_index(f"ix_{table}_line_id", table, ["line_id"])
    op.create_unique_constraint("uq_metrics_id_line", "metrics", ["id", "line_id"])
    op.create_unique_constraint("uq_metrics_line_key", "metrics", ["line_id", "key"])
    for table in LINE_TABLES:
        op.create_foreign_key(f"fk_{table}_line", table, "model_lines", ["line_id", "model_id"], ["id", "model_id"], ondelete="CASCADE")
    op.create_foreign_key("fk_metric_values_line", "metric_values", "metrics", ["metric_id", "line_id"], ["id", "line_id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint("fk_metric_values_line", "metric_values", type_="foreignkey")
    for table in LINE_TABLES:
        op.drop_constraint(f"fk_{table}_line", table, type_="foreignkey")
    op.drop_constraint("uq_metrics_line_key", "metrics", type_="unique")
    op.drop_constraint("uq_metrics_id_line", "metrics", type_="unique")
    for table in (*LINE_TABLES, "metric_values"):
        op.drop_index(f"ix_{table}_line_id", table_name=table)
        op.drop_column(table, "line_id")
    op.execute("TRUNCATE node_positions, event_changes, timeline_events, model_lines")
