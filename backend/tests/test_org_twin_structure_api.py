from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
    GraphEdge,
    GraphNode,
    Metamodel,
    NodeType,
)
from app.api.v1.organisations.models import Organisation
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    _seed_default_metamodel(factory)

    yield factory


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()

    def override_get_db_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_graph_read_filters_nodes_and_edges_by_selected_org_state_date(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    initial_graph_path = _graph_path(organisation_key, "initial_state")
    later_state_key = _create_org_state(client, organisation_key, "2030-01-01")
    later_graph_path = _graph_path(organisation_key, later_state_key)

    initial_node = client.post(
        f"{initial_graph_path}/nodes",
        json={
            "id": "node_initial",
            "name": "Initial node",
            "description": "Visible from reality start",
            "nodeTypeId": "nt_person",
            "position": {"x": 10.5, "y": 20.25},
            "attributes": {"name": "Initial"},
        },
    )
    later_node = client.post(
        f"{later_graph_path}/nodes",
        json={
            "id": "node_later",
            "name": "Later node",
            "nodeTypeId": "nt_person",
            "position": {"x": 30, "y": 40},
            "attributes": {"name": "Later"},
        },
    )
    assert initial_node.status_code == 201
    assert later_node.status_code == 201
    assert initial_node.json()["createDate"] == "2020-01-01"
    assert later_node.json()["createDate"] == "2030-01-01"

    edge_response = client.post(
        f"{later_graph_path}/edges",
        json={
            "id": "edge_later",
            "name": "Later reporting line",
            "description": "Visible only later",
            "edgeTypeId": "et_reports_to",
            "sourceNodeId": "node_later",
            "targetNodeId": "node_initial",
            "attributes": {"weight": 1},
        },
    )
    assert edge_response.status_code == 201
    assert edge_response.json()["createDate"] == "2030-01-01"

    initial_graph = client.get(initial_graph_path).json()
    assert initial_graph["id"] == "reality"
    assert [node["id"] for node in initial_graph["nodes"]] == ["node_initial"]
    assert initial_graph["edges"] == []

    later_graph = client.get(later_graph_path).json()
    assert [node["id"] for node in later_graph["nodes"]] == [
        "node_initial",
        "node_later",
    ]
    assert [edge["id"] for edge in later_graph["edges"]] == ["edge_later"]


def test_type_catalog_returns_active_organisation_metamodel_metadata(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)

    with session_factory() as session:
        organisation = session.scalar(
            select(Organisation).where(
                Organisation.organisation_key == organisation_key,
            ),
        )
        assert organisation is not None
        metamodel = session.scalar(
            select(Metamodel).where(
                Metamodel.organisation_id == organisation.organisation_id,
                Metamodel.deleted_time.is_(None),
            ),
        )
        assert metamodel is not None
        person_type = session.scalar(
            select(NodeType).where(
                NodeType.metamodel_id == metamodel.metamodel_id,
                NodeType.node_type_key == "nt_person",
            ),
        )
        assert person_type is not None
        person_type.display_name = "Organisation person"
        person_type.ui_color = "#ABCDEF"
        person_type.timeserie_id = "id1"
        person_type.timeserie_secondary_id = "id2"
        person_type.timeserie_id_rule = "MEASURED_BY from Goal"

        inactive_node_type = NodeType(
            metamodel_id=metamodel.metamodel_id,
            node_type_key="nt_inactive",
            name="Inactive",
            display_name="Inactive",
            ui_color="#000000",
            ui_shape="rectangle",
            deleted_time=datetime.now(UTC),
        )
        inactive_edge_type = EdgeType(
            metamodel_id=metamodel.metamodel_id,
            edge_type_key="et_inactive",
            name="Inactive edge",
            display_name="Inactive edge",
            ui_style="dashed",
            ui_source_end="none",
            ui_target_end="arrow",
            deleted_time=datetime.now(UTC),
        )
        session.add_all([inactive_node_type, inactive_edge_type])
        session.flush()
        reports_to_type = session.scalar(
            select(EdgeType).where(
                EdgeType.metamodel_id == metamodel.metamodel_id,
                EdgeType.edge_type_key == "et_reports_to",
            ),
        )
        assert reports_to_type is not None
        session.add(
            AllowedConnection(
                metamodel_id=metamodel.metamodel_id,
                edge_type_id=reports_to_type.edge_type_id,
                source_node_type_id=person_type.node_type_id,
                target_node_type_id=person_type.node_type_id,
                deleted_time=datetime.now(UTC),
            ),
        )
        session.commit()

    response = client.get(f"{_graph_path(organisation_key, 'initial_state')}/types")

    assert response.status_code == 200
    assert response.json() == {
        "nodeTypes": [
            {
                "id": "nt_person",
                "name": "Person",
                "displayName": "Organisation person",
                "color": "#ABCDEF",
                "shape": "rectangle",
                "timeserieId": "id1",
                "timeserieSecondaryId": "id2",
                "timeserieIdRule": "MEASURED_BY from Goal",
            },
            {
                "id": "nt_team",
                "name": "Team",
                "displayName": "Team",
                "color": "#D9F99D",
                "shape": "ellipse",
                "timeserieId": None,
                "timeserieSecondaryId": None,
                "timeserieIdRule": None,
            },
        ],
        "edgeTypes": [
            {
                "id": "et_reports_to",
                "name": "Reports to",
                "displayName": "Reports to",
                "style": "solid",
                "sourceEnd": "none",
                "targetEnd": "arrow",
            },
        ],
        "allowedConnections": [
            {
                "edgeTypeId": "et_reports_to",
                "sourceNodeTypeId": "nt_person",
                "targetNodeTypeId": "nt_person",
            }
        ],
    }


def test_type_catalog_rejects_allowed_connection_referencing_inactive_type(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)

    with session_factory() as session:
        organisation = session.scalar(
            select(Organisation).where(
                Organisation.organisation_key == organisation_key,
            ),
        )
        assert organisation is not None
        metamodel = session.scalar(
            select(Metamodel).where(
                Metamodel.organisation_id == organisation.organisation_id,
                Metamodel.deleted_time.is_(None),
            ),
        )
        assert metamodel is not None
        person_type = session.scalar(
            select(NodeType).where(
                NodeType.metamodel_id == metamodel.metamodel_id,
                NodeType.node_type_key == "nt_person",
            ),
        )
        assert person_type is not None
        inactive_edge_type = EdgeType(
            metamodel_id=metamodel.metamodel_id,
            edge_type_key="et_inactive",
            name="Inactive edge",
            display_name="Inactive edge",
            ui_style="solid",
            ui_source_end="none",
            ui_target_end="arrow",
            deleted_time=datetime.now(UTC),
        )
        session.add(inactive_edge_type)
        session.flush()
        session.add(
            AllowedConnection(
                metamodel_id=metamodel.metamodel_id,
                edge_type_id=inactive_edge_type.edge_type_id,
                source_node_type_id=person_type.node_type_id,
                target_node_type_id=person_type.node_type_id,
            ),
        )
        session.commit()

    response = client.get(f"{_graph_path(organisation_key, 'initial_state')}/types")

    assert response.status_code == 500
    assert (
        response.json()["detail"]
        == "Allowed connection references a missing active type."
    )


def test_type_catalog_validates_missing_parent_resources(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)

    missing_org_response = client.get(
        f"{_graph_path('missing', 'initial_state')}/types",
    )
    assert missing_org_response.status_code == 404
    assert (
        client.get(
            (
                f"/api/v1/organisations/{organisation_key}/scenarios/missing/"
                "org-states/initial_state/graph/types"
            ),
        ).status_code
        == 404
    )
    missing_state_response = client.get(
        f"{_graph_path(organisation_key, 'missing')}/types",
    )
    assert missing_state_response.status_code == 404


def test_type_catalog_uses_existing_missing_metamodel_error_behavior(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)

    with session_factory() as session:
        organisation = session.scalar(
            select(Organisation).where(
                Organisation.organisation_key == organisation_key,
            ),
        )
        assert organisation is not None
        metamodel = session.scalar(
            select(Metamodel).where(
                Metamodel.organisation_id == organisation.organisation_id,
                Metamodel.deleted_time.is_(None),
            ),
        )
        assert metamodel is not None
        metamodel.deleted_time = datetime.now(UTC)
        session.commit()

    response = client.get(f"{_graph_path(organisation_key, 'initial_state')}/types")

    assert response.status_code == 500
    assert (
        response.json()["detail"]
        == "Active organisation metamodel is not configured."
    )


def test_node_edge_crud_and_bulk_position_update(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    graph_path = _graph_path(organisation_key, "initial_state")

    first_node = client.post(
        f"{graph_path}/nodes",
        json={
            "id": "node_ceo",
            "name": "CEO",
            "nodeTypeId": "nt_person",
            "position": {"x": 10.5, "y": 20.25},
            "attributes": {"name": "CEO"},
        },
    )
    second_node = client.post(
        f"{graph_path}/nodes",
        json={
            "id": "node_report",
            "name": "Report",
            "nodeTypeId": "nt_person",
            "position": {"x": 30, "y": 40},
            "attributes": {"name": "Report"},
        },
    )
    assert first_node.status_code == 201
    assert second_node.status_code == 201
    assert first_node.json() == {
        "id": "node_ceo",
        "name": "CEO",
        "description": "",
        "nodeTypeId": "nt_person",
        "createDate": "2020-01-01",
        "deleteDate": None,
        "position": {"x": 10.5, "y": 20.25},
        "attributes": {"name": "CEO"},
        "timeserieId": None,
        "timeserieSecondaryId": None,
    }

    edge_response = client.post(
        f"{graph_path}/edges",
        json={
            "id": "edge_reports_to",
            "name": "Reports to",
            "edgeTypeId": "et_reports_to",
            "sourceNodeId": "node_report",
            "targetNodeId": "node_ceo",
            "attributes": {"weight": 1},
        },
    )
    assert edge_response.status_code == 201
    assert edge_response.json() == {
        "id": "edge_reports_to",
        "name": "Reports to",
        "description": "",
        "edgeTypeId": "et_reports_to",
        "sourceNodeId": "node_report",
        "targetNodeId": "node_ceo",
        "createDate": "2020-01-01",
        "deleteDate": None,
        "attributes": {"weight": 1},
    }

    patch_node_response = client.patch(
        f"{graph_path}/nodes/node_ceo",
        json={
            "name": "Chief Executive",
            "position": {"x": -5, "y": 0},
            "attributes": {"name": "Chief Executive"},
        },
    )
    assert patch_node_response.status_code == 200
    assert patch_node_response.json()["name"] == "Chief Executive"
    assert patch_node_response.json()["position"] == {"x": -5.0, "y": 0.0}
    assert patch_node_response.json()["attributes"] == {"name": "Chief Executive"}

    bulk_response = client.patch(
        f"{graph_path}/positions",
        json={
            "positions": [
                {"nodeId": "node_ceo", "x": 100, "y": 200},
                {"nodeId": "node_report", "x": 300, "y": 400},
            ],
        },
    )
    assert bulk_response.status_code == 200
    nodes_by_id = {node["id"]: node for node in bulk_response.json()["nodes"]}
    assert nodes_by_id["node_ceo"]["position"] == {"x": 100.0, "y": 200.0}
    assert nodes_by_id["node_report"]["position"] == {"x": 300.0, "y": 400.0}

    patch_edge_response = client.patch(
        f"{graph_path}/edges/edge_reports_to",
        json={"name": "Updated reporting line", "attributes": {"weight": 2}},
    )
    assert patch_edge_response.status_code == 200
    assert patch_edge_response.json()["name"] == "Updated reporting line"
    assert patch_edge_response.json()["attributes"] == {"weight": 2}

    assert client.delete(f"{graph_path}/edges/edge_reports_to").status_code == 204
    assert client.delete(f"{graph_path}/nodes/node_report").status_code == 204
    graph_response = client.get(graph_path)
    assert graph_response.status_code == 200
    assert [node["id"] for node in graph_response.json()["nodes"]] == ["node_ceo"]
    assert graph_response.json()["edges"] == []

    with session_factory() as session:
        deleted_node = session.scalar(
            select(GraphNode).where(GraphNode.node_key == "node_report")
        )
        deleted_edge = session.scalar(
            select(GraphEdge).where(GraphEdge.edge_key == "edge_reports_to")
        )
        assert deleted_node is not None and deleted_edge is not None
        assert deleted_node.deleted_time is not None
        assert deleted_node.delete_date is None
        assert deleted_edge.deleted_time is not None
        assert deleted_edge.delete_date is None

    later_state_key = _create_org_state(client, organisation_key, "2020-01-02")
    later_graph = client.get(_graph_path(organisation_key, later_state_key)).json()
    assert [node["id"] for node in later_graph["nodes"]] == ["node_ceo"]
    assert later_graph["edges"] == []


def test_same_day_node_deletion_soft_deletes_connected_edges(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    graph_path = _graph_path(organisation_key, "initial_state")
    for node_id in ("node_a", "node_b"):
        assert (
            client.post(
                f"{graph_path}/nodes",
                json={"id": node_id, "name": node_id, "nodeTypeId": "nt_person"},
            ).status_code
            == 201
        )
    assert (
        client.post(
            f"{graph_path}/edges",
            json={
                "id": "edge_a",
                "name": "Edge",
                "edgeTypeId": "et_reports_to",
                "sourceNodeId": "node_a",
                "targetNodeId": "node_b",
            },
        ).status_code
        == 201
    )

    assert client.delete(f"{graph_path}/nodes/node_b").status_code == 204

    refreshed_graph = client.get(graph_path).json()
    assert [node["id"] for node in refreshed_graph["nodes"]] == ["node_a"]
    assert refreshed_graph["edges"] == []

    with session_factory() as session:
        deleted_node = session.scalar(
            select(GraphNode).where(GraphNode.node_key == "node_b")
        )
        deleted_edge = session.scalar(
            select(GraphEdge).where(GraphEdge.edge_key == "edge_a")
        )
        assert deleted_node is not None and deleted_edge is not None
        assert deleted_node.deleted_time is not None
        assert deleted_node.delete_date is None
        assert deleted_edge.deleted_time is not None
        assert deleted_edge.delete_date is None


def test_graph_history_and_logical_deletion_preserve_lifetimes(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    initial_graph_path = _graph_path(organisation_key, "initial_state")
    deletion_state_key = _create_org_state(client, organisation_key, "2030-01-01")
    after_state_key = _create_org_state(client, organisation_key, "2030-01-02")

    for node_id, name in [("node_b", "Beta"), ("node_a", "Alpha")]:
        assert (
            client.post(
                f"{initial_graph_path}/nodes",
                json={"id": node_id, "name": name, "nodeTypeId": "nt_person"},
            ).status_code
            == 201
        )
    assert (
        client.post(
            f"{initial_graph_path}/edges",
            json={
                "id": "edge_a",
                "name": "Reports to",
                "edgeTypeId": "et_reports_to",
                "sourceNodeId": "node_b",
                "targetNodeId": "node_a",
            },
        ).status_code
        == 201
    )

    deletion_path = _graph_path(organisation_key, deletion_state_key)
    assert client.delete(f"{deletion_path}/nodes/node_b").status_code == 204

    at_deletion = client.get(deletion_path).json()
    assert {node["id"] for node in at_deletion["nodes"]} == {"node_a", "node_b"}
    assert [edge["id"] for edge in at_deletion["edges"]] == ["edge_a"]

    after_deletion = client.get(_graph_path(organisation_key, after_state_key)).json()
    assert [node["id"] for node in after_deletion["nodes"]] == ["node_a"]
    assert after_deletion["edges"] == []

    history_response = client.get(_history_path(organisation_key))
    assert history_response.status_code == 200
    history = history_response.json()
    assert [node["id"] for node in history["nodes"]] == ["node_a", "node_b"]
    assert history["nodes"][1]["createDate"] == "2020-01-01"
    assert history["nodes"][1]["deleteDate"] == "2030-01-01"
    assert history["edges"][0]["sourceNodeId"] == "node_b"
    assert history["edges"][0]["targetNodeId"] == "node_a"
    assert history["edges"][0]["deleteDate"] == "2030-01-01"


def test_graph_history_excludes_persistence_soft_deleted_elements(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    graph_path = _graph_path(organisation_key, "initial_state")
    for node_id in ("node_a", "node_b"):
        assert (
            client.post(
                f"{graph_path}/nodes",
                json={"id": node_id, "name": node_id, "nodeTypeId": "nt_person"},
            ).status_code
            == 201
        )
    assert (
        client.post(
            f"{graph_path}/edges",
            json={
                "id": "edge_a",
                "name": "Edge",
                "edgeTypeId": "et_reports_to",
                "sourceNodeId": "node_a",
                "targetNodeId": "node_b",
            },
        ).status_code
        == 201
    )

    with session_factory() as session:
        node = session.scalar(select(GraphNode).where(GraphNode.node_key == "node_b"))
        edge = session.scalar(select(GraphEdge).where(GraphEdge.edge_key == "edge_a"))
        assert node is not None and edge is not None
        node.deleted_time = datetime.now(UTC)
        edge.deleted_time = datetime.now(UTC)
        session.commit()

    history = client.get(_history_path(organisation_key)).json()
    assert [node["id"] for node in history["nodes"]] == ["node_a"]
    assert history["edges"] == []


def test_graph_lifetime_validation_and_same_day_node_cleanup(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    graph_path = _graph_path(organisation_key, "initial_state")
    later_state_key = _create_org_state(client, organisation_key, "2030-01-01")
    for node_id in ("node_a", "node_b"):
        assert (
            client.post(
                f"{graph_path}/nodes",
                json={"id": node_id, "name": node_id, "nodeTypeId": "nt_person"},
            ).status_code
            == 201
        )

    with session_factory() as session:
        node_b = session.scalar(select(GraphNode).where(GraphNode.node_key == "node_b"))
        assert node_b is not None
        node_b.delete_date = date(2025, 1, 1)
        session.commit()

    invalid_edge = client.post(
        f"{graph_path}/edges",
        json={
            "id": "edge_invalid",
            "name": "Invalid lifetime",
            "edgeTypeId": "et_reports_to",
            "sourceNodeId": "node_a",
            "targetNodeId": "node_b",
        },
    )
    assert invalid_edge.status_code == 400
    assert "cannot extend beyond" in invalid_edge.json()["detail"]

    with session_factory() as session:
        node_b = session.scalar(select(GraphNode).where(GraphNode.node_key == "node_b"))
        assert node_b is not None
        node_b.delete_date = None
        session.commit()

    later_path = _graph_path(organisation_key, later_state_key)
    assert (
        client.post(
            f"{later_path}/edges",
            json={
                "id": "edge_future",
                "name": "Future edge",
                "edgeTypeId": "et_reports_to",
                "sourceNodeId": "node_a",
                "targetNodeId": "node_b",
            },
        ).status_code
        == 201
    )
    same_day_node_delete = client.delete(f"{graph_path}/nodes/node_a")
    assert same_day_node_delete.status_code == 204

    with session_factory() as session:
        deleted_node = session.scalar(
            select(GraphNode).where(GraphNode.node_key == "node_a")
        )
        deleted_edge = session.scalar(
            select(GraphEdge).where(GraphEdge.edge_key == "edge_future")
        )
        assert deleted_node is not None and deleted_edge is not None
        assert deleted_node.deleted_time is not None
        assert deleted_edge.deleted_time is not None


def test_scenario_graph_endpoints_validate_ownership_and_return_type_catalog(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    history_path = _history_path(organisation_key)
    type_path = history_path.removesuffix("/history") + "/types"

    assert client.get(history_path).status_code == 200
    type_response = client.get(type_path)
    assert type_response.status_code == 200
    assert [item["id"] for item in type_response.json()["nodeTypes"]] == [
        "nt_person",
        "nt_team",
    ]
    assert client.get(_history_path("missing")).status_code == 404
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/missing/graph/history"
        ).status_code
        == 404
    )


def test_graph_node_patch_updates_timeserie_links_by_stable_keys(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    graph_path = _graph_path(organisation_key, "initial_state")
    timeseries_path = (
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"
    )

    for timeserie_id in ["metric_primary", "metric_secondary"]:
        response = client.post(
            timeseries_path,
            json={
                "id": timeserie_id,
                "name": timeserie_id,
                "timeUnit": "month",
                "valueUnit": "number",
            },
        )
        assert response.status_code == 201

    assert (
        client.post(
            f"{graph_path}/nodes",
            json={"id": "node_metric", "name": "Metric", "nodeTypeId": "nt_person"},
        ).status_code
        == 201
    )

    link_response = client.patch(
        f"{graph_path}/nodes/node_metric",
        json={
            "timeserieId": "metric_primary",
            "timeserieSecondaryId": "metric_secondary",
        },
    )

    assert link_response.status_code == 200
    assert link_response.json()["timeserieId"] == "metric_primary"
    assert link_response.json()["timeserieSecondaryId"] == "metric_secondary"
    graph_response = client.get(graph_path)
    assert graph_response.status_code == 200
    assert graph_response.json()["nodes"][0]["timeserieId"] == "metric_primary"

    clear_response = client.patch(
        f"{graph_path}/nodes/node_metric",
        json={"timeserieId": None, "timeserieSecondaryId": None},
    )

    assert clear_response.status_code == 200
    assert clear_response.json()["timeserieId"] is None
    assert clear_response.json()["timeserieSecondaryId"] is None
    assert (
        client.patch(
            f"{graph_path}/nodes/node_metric",
            json={"timeserieId": "missing"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"{graph_path}/nodes/node_metric",
            json={"timeserieId": "  "},
        ).status_code
        == 422
    )


def test_structure_endpoints_validate_conflicts_and_missing_resources(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    graph_path = _graph_path(organisation_key, "initial_state")

    assert client.get(_graph_path("missing", "initial_state")).status_code == 404
    assert (
        client.post(
            f"{graph_path}/nodes",
            json={"id": "node_blank", "name": "   ", "nodeTypeId": "nt_person"},
        ).status_code
        == 422
    )

    node_payload = {
        "id": "node_a",
        "name": "Node A",
        "nodeTypeId": "nt_person",
        "position": {"x": 0, "y": 0},
    }
    assert client.post(f"{graph_path}/nodes", json=node_payload).status_code == 201
    assert client.post(f"{graph_path}/nodes", json=node_payload).status_code == 409
    assert (
        client.post(
            f"{graph_path}/nodes",
            json={
                "id": "node_missing_type",
                "name": "Missing",
                "nodeTypeId": "missing",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{graph_path}/nodes",
            json={
                "id": "node_bad_position",
                "name": "Bad position",
                "nodeTypeId": "nt_person",
                "position": {"x": 100_001, "y": 0},
            },
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{graph_path}/positions",
            json={
                "positions": [
                    {"nodeId": "node_a", "x": 1, "y": 1},
                    {"nodeId": "node_a", "x": 2, "y": 2},
                ],
            },
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"{graph_path}/positions",
            json={"positions": [{"nodeId": "missing", "x": 1, "y": 1}]},
        ).status_code
        == 404
    )


def test_edge_validation_rejects_duplicates_missing_nodes_and_disallowed_connection(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    graph_path = _graph_path(organisation_key, "initial_state")

    assert (
        client.post(
            f"{graph_path}/nodes",
            json={"id": "node_person", "name": "Person", "nodeTypeId": "nt_person"},
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"{graph_path}/nodes",
            json={"id": "node_team", "name": "Team", "nodeTypeId": "nt_team"},
        ).status_code
        == 201
    )

    valid_edge = {
        "id": "edge_person",
        "name": "Person reports",
        "edgeTypeId": "et_reports_to",
        "sourceNodeId": "node_person",
        "targetNodeId": "node_person",
    }
    assert client.post(f"{graph_path}/edges", json=valid_edge).status_code == 201
    assert client.post(f"{graph_path}/edges", json=valid_edge).status_code == 409
    assert (
        client.patch(
            f"{graph_path}/nodes/node_person",
            json={"nodeTypeId": "nt_team"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"{graph_path}/edges",
            json={
                "id": "edge_missing_node",
                "name": "Missing node",
                "edgeTypeId": "et_reports_to",
                "sourceNodeId": "missing",
                "targetNodeId": "node_person",
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{graph_path}/edges",
            json={
                "id": "edge_disallowed",
                "name": "Disallowed",
                "edgeTypeId": "et_reports_to",
                "sourceNodeId": "node_person",
                "targetNodeId": "node_team",
            },
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"{graph_path}/edges/edge_person",
            json={"targetNodeId": "node_team"},
        ).status_code
        == 400
    )


def _seed_default_metamodel(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        metamodel = Metamodel(version=1)
        session.add(metamodel)
        session.flush()

        person_type = NodeType(
            metamodel_id=metamodel.metamodel_id,
            node_type_key="nt_person",
            name="Person",
            display_name="Person",
            ui_color="#FECDC2",
            ui_shape="rectangle",
        )
        team_type = NodeType(
            metamodel_id=metamodel.metamodel_id,
            node_type_key="nt_team",
            name="Team",
            display_name="Team",
            ui_color="#D9F99D",
            ui_shape="ellipse",
        )
        edge_type = EdgeType(
            metamodel_id=metamodel.metamodel_id,
            edge_type_key="et_reports_to",
            name="Reports to",
            display_name="Reports to",
            ui_style="solid",
            ui_source_end="none",
            ui_target_end="arrow",
        )
        session.add_all([person_type, team_type, edge_type])
        session.flush()
        session.add(
            AllowedConnection(
                metamodel_id=metamodel.metamodel_id,
                edge_type_id=edge_type.edge_type_id,
                source_node_type_id=person_type.node_type_id,
                target_node_type_id=person_type.node_type_id,
            ),
        )
        session.commit()


def _create_organisation(client: TestClient) -> str:
    response = client.post("/api/v1/organisations", json={"name": "Acme Corp"})
    assert response.status_code == 201
    organisation_key = response.json()["id"]
    assert isinstance(organisation_key, str)
    return organisation_key


def _create_org_state(
    client: TestClient,
    organisation_key: str,
    target_date: str,
) -> str:
    response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
        json={"name": f"State {target_date}", "targetDate": target_date},
    )
    assert response.status_code == 201
    org_state_key = response.json()["id"]
    assert isinstance(org_state_key, str)
    return org_state_key


def _graph_path(organisation_key: str, org_state_key: str) -> str:
    return (
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        f"org-states/{org_state_key}/graph"
    )


def _history_path(organisation_key: str) -> str:
    return (
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/graph/history"
    )
