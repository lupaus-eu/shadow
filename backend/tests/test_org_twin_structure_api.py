from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
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
            },
            {
                "id": "nt_team",
                "name": "Team",
                "displayName": "Team",
                "color": "#D9F99D",
                "shape": "ellipse",
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
    }


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


def test_node_edge_crud_and_bulk_position_update(client: TestClient) -> None:
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
        "position": {"x": 10.5, "y": 20.25},
        "attributes": {"name": "CEO"},
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
