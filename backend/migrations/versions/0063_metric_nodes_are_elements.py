"""``metrics.node_id`` holds an element id: drop its foreign key to the old ``nodes`` table.

Nodes live in events now (ADR-0048); the ``nodes`` table no longer changes and is dropped by ticket 08.
A metric tied to a node keeps the column but not the foreign key, and its value is remapped from an old
``nodes.id`` to the node's element id by the rules migration 0061 used to build the events: a baseline
node keeps its id; a fork node whose ``origin_node_id`` leads (through the origin chain) to a node of its
base uses that node's element id; every other node keeps its own id. A value that is not the element id of
any ``add_node`` change (a node added after 0061 by the old routes, which no event holds) becomes NULL,
as the old foreign key did when its node was deleted.

Downgrade recomputes the same mapping, points each metric at the old node row of its line that carries the
element id (NULL where there is none: a node added by events after this migration has no row), and
recreates the foreign key.

Revision ID: 0063
Revises: 0062
"""

from collections import defaultdict
from uuid import UUID

import sqlalchemy as sa
from alembic import op


revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def _element_ids(bind) -> tuple[dict[UUID, UUID], dict[UUID, UUID]]:
    """Old node id -> element id, and old node id -> the version it belongs to (the rules of migration 0061)."""
    versions = defaultdict(list)
    for row in bind.execute(sa.text("SELECT id, model_id, is_baseline, base_version_id FROM model_versions ORDER BY created_at, id")).mappings():
        versions[row["model_id"]].append(row)
    nodes = defaultdict(list)
    version_of: dict[UUID, UUID] = {}
    for row in bind.execute(sa.text("SELECT id, version_id, origin_node_id FROM nodes ORDER BY created_at, id")).mappings():
        nodes[row["version_id"]].append(row)
        version_of[row["id"]] = row["version_id"]
    element_of: dict[UUID, UUID] = {}
    graph: dict[object, set[UUID]] = {}  # version id -> element ids of its graph
    for own in versions.values():
        baseline = next((row for row in own if row["is_baseline"]), None)
        base_id = baseline["id"] if baseline else object()
        for node in nodes.get(base_id, []) if baseline else []:
            element_of[node["id"]] = node["id"]
        graph[base_id] = {node["id"] for node in nodes.get(base_id, [])} if baseline else set()
        ids = {row["id"] for row in own}
        pending = [row for row in own if not row["is_baseline"]]
        while pending:
            ready = next((row for row in pending if (row["base_version_id"] if row["base_version_id"] in ids else base_id) in graph), None)
            if ready is None:
                ready, base = pending[0], base_id
            else:
                base = ready["base_version_id"] if ready["base_version_id"] in ids else base_id
            pending.remove(ready)
            fork_nodes: set[UUID] = set()
            for node in nodes.get(ready["id"], []):
                origin = element_of.get(node["origin_node_id"]) if node["origin_node_id"] else None
                element = origin if origin in graph[base] and origin not in fork_nodes else node["id"]
                element_of[node["id"]] = element
                fork_nodes.add(element)
            graph[ready["id"]] = fork_nodes
    return element_of, version_of


def upgrade() -> None:
    bind = op.get_bind()
    op.drop_constraint("metrics_node_id_fkey", "metrics", type_="foreignkey")
    element_of, _ = _element_ids(bind)
    for row in bind.execute(sa.text("SELECT id, node_id FROM metrics WHERE node_id IS NOT NULL")).mappings().all():
        element = element_of.get(row["node_id"])
        if element != row["node_id"]:
            bind.execute(sa.text("UPDATE metrics SET node_id = :node WHERE id = :id"), {"node": element, "id": row["id"]})
    op.execute("UPDATE metrics SET node_id = NULL WHERE node_id IS NOT NULL AND node_id NOT IN (SELECT element_id FROM event_changes WHERE op = 'add_node')")


def downgrade() -> None:
    bind = op.get_bind()
    element_of, version_of = _element_ids(bind)
    old_node = {(version_of[node], element): node for node, element in element_of.items()}
    for row in bind.execute(sa.text("SELECT id, line_id, node_id FROM metrics WHERE node_id IS NOT NULL")).mappings().all():
        bind.execute(sa.text("UPDATE metrics SET node_id = :node WHERE id = :id"), {"node": old_node.get((row["line_id"], row["node_id"])), "id": row["id"]})
    op.create_foreign_key("metrics_node_id_fkey", "metrics", "nodes", ["node_id"], ["id"], ondelete="SET NULL")
