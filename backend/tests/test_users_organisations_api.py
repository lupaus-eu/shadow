import logging
from collections.abc import Iterator
from datetime import date
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import (
    Event,
    OrgState,
    Scenario,
    Timeserie,
    TimeserieValue,
)
from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
    Graph,
    GraphEdge,
    GraphNode,
    Metamodel,
    NodeType,
    TypeAttribute,
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


def _seed_default_metamodel(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        metamodel = Metamodel(version=1)
        session.add(metamodel)
        session.flush()

        node_type = NodeType(
            metamodel_id=metamodel.metamodel_id,
            node_type_key="nt_person",
            name="Person",
            display_name="Person",
            ui_color="#FECDC2",
            ui_shape="rectangle",
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
        session.add_all([node_type, edge_type])
        session.flush()

        session.add_all(
            [
                TypeAttribute(
                    metamodel_id=metamodel.metamodel_id,
                    owner_kind="node_type",
                    owner_node_type_id=node_type.node_type_id,
                    attribute_key="a_name",
                    name="Name",
                    display_name="Name",
                    data_type="string",
                    mandatory=True,
                    max_length=100,
                    multiline=False,
                ),
                AllowedConnection(
                    metamodel_id=metamodel.metamodel_id,
                    edge_type_id=edge_type.edge_type_id,
                    source_node_type_id=node_type.node_type_id,
                    target_node_type_id=node_type.node_type_id,
                ),
            ],
        )
        session.commit()


def test_users_crud_excludes_soft_deleted_rows(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/users",
        json={"name": "  Ada Lovelace  ", "role": "admin"},
    )
    assert create_response.status_code == 201
    created_user = create_response.json()
    assert created_user == {"id": 1, "name": "Ada Lovelace", "role": "admin"}

    user_id = created_user["id"]
    assert client.get(f"/api/v1/users/{user_id}").json() == created_user
    assert client.get("/api/v1/users").json() == [created_user]

    patch_response = client.patch(
        f"/api/v1/users/{user_id}",
        json={"name": "Grace Hopper", "role": "consultant"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": user_id,
        "name": "Grace Hopper",
        "role": "consultant",
    }

    delete_response = client.delete(f"/api/v1/users/{user_id}")
    assert delete_response.status_code == 204
    assert client.get("/api/v1/users").json() == []
    assert client.get(f"/api/v1/users/{user_id}").status_code == 404


def test_user_create_rejects_invalid_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/users",
        json={"name": "Ada Lovelace", "role": "owner"},
    )

    assert response.status_code == 422


def test_organisation_crud_returns_frontend_dto_and_excludes_deleted_rows(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/v1/organisations",
        json={"name": "  Acme Corp  "},
    )
    assert create_response.status_code == 201
    created_org = create_response.json()
    assert created_org["id"].startswith("org_")
    assert created_org["name"] == "Acme Corp"

    organisation_key = created_org["id"]
    assert client.get(f"/api/v1/organisations/{organisation_key}").json() == created_org
    assert client.get("/api/v1/organisations").json() == [created_org]

    patch_response = client.patch(
        f"/api/v1/organisations/{organisation_key}",
        json={"name": "Acme Updated"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": organisation_key,
        "name": "Acme Updated",
    }

    delete_response = client.delete(f"/api/v1/organisations/{organisation_key}")
    assert delete_response.status_code == 204
    assert client.get("/api/v1/organisations").json() == []
    assert client.get(f"/api/v1/organisations/{organisation_key}").status_code == 404


def test_organisation_create_adds_default_workspace_data_and_copies_metamodel(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    create_response = client.post(
        "/api/v1/organisations",
        json={"name": "Acme Corp"},
    )
    assert create_response.status_code == 201
    created_payload = cast(dict[str, object], create_response.json())
    organisation_key_value = created_payload["id"]
    assert isinstance(organisation_key_value, str)
    organisation_key = organisation_key_value

    scenarios_response = client.get(
        f"/api/v1/organisations/{organisation_key}/scenarios",
    )
    assert scenarios_response.status_code == 200
    assert scenarios_response.json() == [
        {
            "id": "reality",
            "name": "Reality",
            "description": "The reality of the organisation",
            "protected": True,
        },
    ]

    org_states_response = client.get(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
    )
    assert org_states_response.status_code == 200
    assert org_states_response.json() == [
        {
            "id": "initial_state",
            "name": "Initial state",
            "description": "Initial state of reality",
            "targetDate": "2020-01-01",
        },
    ]

    with session_factory() as session:
        organisation = session.scalar(
            select(Organisation).where(
                Organisation.organisation_key == organisation_key,
            ),
        )
        assert organisation is not None
        scenario = session.scalar(
            select(Scenario).where(
                Scenario.organisation_id == organisation.organisation_id,
                Scenario.scenario_key == "reality",
            ),
        )
        assert scenario is not None
        org_state = session.scalar(
            select(OrgState).where(
                OrgState.scenario_id == scenario.scenario_id,
                OrgState.org_state_key == "initial_state",
            ),
        )
        assert org_state is not None
        assert scenario.initial_state_id == org_state.org_state_id

        copied_metamodels = session.scalars(
            select(Metamodel).where(
                Metamodel.organisation_id == organisation.organisation_id,
            ),
        ).all()
        assert len(copied_metamodels) == 1
        copied_metamodel = copied_metamodels[0]

        copied_node_types = session.scalars(
            select(NodeType).where(
                NodeType.metamodel_id == copied_metamodel.metamodel_id,
            ),
        ).all()
        copied_edge_types = session.scalars(
            select(EdgeType).where(
                EdgeType.metamodel_id == copied_metamodel.metamodel_id,
            ),
        ).all()
        copied_type_attributes = session.scalars(
            select(TypeAttribute).where(
                TypeAttribute.metamodel_id == copied_metamodel.metamodel_id,
            ),
        ).all()
        copied_allowed_connections = session.scalars(
            select(AllowedConnection).where(
                AllowedConnection.metamodel_id == copied_metamodel.metamodel_id,
            ),
        ).all()

        assert [item.node_type_key for item in copied_node_types] == ["nt_person"]
        assert [item.edge_type_key for item in copied_edge_types] == ["et_reports_to"]
        assert [item.attribute_key for item in copied_type_attributes] == ["a_name"]
        assert len(copied_allowed_connections) == 1


def test_organisation_create_rolls_back_when_default_metamodel_is_invalid(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        node_type = session.scalar(
            select(NodeType).where(NodeType.ui_shape == "rectangle"),
        )
        assert node_type is not None
        node_type.ui_shape = "triangle"
        session.commit()

    response = client.post("/api/v1/organisations", json={"name": "Acme Corp"})

    assert response.status_code == 500
    assert client.get("/api/v1/organisations").json() == []


def test_duplicate_active_organisation_name_returns_409(client: TestClient) -> None:
    first_response = client.post("/api/v1/organisations", json={"name": "Acme Corp"})
    assert first_response.status_code == 201

    duplicate_response = client.post(
        "/api/v1/organisations",
        json={"name": "acme corp"},
    )
    assert duplicate_response.status_code == 409


def test_soft_deleted_organisation_name_can_be_reused(client: TestClient) -> None:
    first_response = client.post("/api/v1/organisations", json={"name": "Acme Corp"})
    assert first_response.status_code == 201

    organisation_key = first_response.json()["id"]
    assert client.delete(f"/api/v1/organisations/{organisation_key}").status_code == 204

    second_response = client.post("/api/v1/organisations", json={"name": "acme corp"})
    assert second_response.status_code == 201
    assert second_response.json()["name"] == "acme corp"


def test_patch_organisation_rejects_duplicate_active_name(
    client: TestClient,
) -> None:
    first_response = client.post("/api/v1/organisations", json={"name": "Acme Corp"})
    second_response = client.post("/api/v1/organisations", json={"name": "Globex"})
    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = client.patch(
        f"/api/v1/organisations/{second_response.json()['id']}",
        json={"name": "ACME CORP"},
    )

    assert response.status_code == 409


def test_scenario_crud_uses_stable_keys_and_excludes_soft_deleted_rows(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)

    create_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "  Future plan  ", "description": "Expansion"},
    )
    assert create_response.status_code == 201
    created_scenario = create_response.json()
    assert created_scenario["id"].startswith("scenario_")
    assert created_scenario == {
        "id": created_scenario["id"],
        "name": "Future plan",
        "description": "Expansion",
        "protected": False,
    }

    scenario_key = created_scenario["id"]
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}",
        ).json()
        == created_scenario
    )
    assert created_scenario in client.get(
        f"/api/v1/organisations/{organisation_key}/scenarios",
    ).json()

    patch_response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}",
        json={"name": "Updated future", "description": "Updated"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": scenario_key,
        "name": "Updated future",
        "description": "Updated",
        "protected": False,
    }

    delete_response = client.delete(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}",
    )
    assert delete_response.status_code == 204
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}",
        ).status_code
        == 404
    )
    listed_ids = [
        item["id"]
        for item in client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios",
        ).json()
    ]
    assert scenario_key not in listed_ids


def test_scenario_endpoints_return_404_for_missing_parents_and_resources(
    client: TestClient,
) -> None:
    assert client.get("/api/v1/organisations/missing/scenarios").status_code == 404

    organisation_key = _create_organisation(client)
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/missing",
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            "org-states/missing",
        ).status_code
        == 404
    )


def test_scenario_create_and_patch_validate_blank_names(client: TestClient) -> None:
    organisation_key = _create_organisation(client)

    create_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "   ", "description": "Nope"},
    )
    assert create_response.status_code == 422

    patch_response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality",
        json={"name": "   "},
    )
    assert patch_response.status_code == 422


def test_protected_scenario_patch_persists_and_delete_returns_409(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)

    patch_response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality",
        json={
            "name": "Reality edited",
            "description": "Protected scenario remains editable",
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": "reality",
        "name": "Reality edited",
        "description": "Protected scenario remains editable",
        "protected": True,
    }
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality",
        ).json()
        == patch_response.json()
    )

    delete_response = client.delete(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality",
    )
    assert delete_response.status_code == 409


def test_scenario_copy_copies_bounded_org_states_and_graph_snapshots(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    source_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "Source scenario", "description": "Source"},
    )
    assert source_response.status_code == 201
    source_scenario_key_value = cast(dict[str, object], source_response.json())["id"]
    assert isinstance(source_scenario_key_value, str)
    source_scenario_key = source_scenario_key_value

    deleted_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/"
        f"{source_scenario_key}/org-states",
        json={"name": "Deleted state", "targetDate": "2029-01-01"},
    )
    first_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/"
        f"{source_scenario_key}/org-states",
        json={"name": "First state", "targetDate": "2030-01-01"},
    )
    boundary_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/"
        f"{source_scenario_key}/org-states",
        json={"name": "Boundary state", "targetDate": "2030-02-01"},
    )
    later_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/"
        f"{source_scenario_key}/org-states",
        json={"name": "Later state", "targetDate": "2030-03-01"},
    )
    assert deleted_state_response.status_code == 201
    assert first_state_response.status_code == 201
    assert boundary_state_response.status_code == 201
    assert later_state_response.status_code == 201

    deleted_state_key_value = cast(dict[str, object], deleted_state_response.json())[
        "id"
    ]
    first_state_key_value = cast(dict[str, object], first_state_response.json())["id"]
    boundary_state_key_value = cast(
        dict[str, object],
        boundary_state_response.json(),
    )["id"]
    assert isinstance(deleted_state_key_value, str)
    assert isinstance(first_state_key_value, str)
    assert isinstance(boundary_state_key_value, str)
    deleted_state_key = deleted_state_key_value
    first_state_key = first_state_key_value
    boundary_state_key = boundary_state_key_value
    assert (
        client.delete(
            f"/api/v1/organisations/{organisation_key}/scenarios/"
            f"{source_scenario_key}/org-states/{deleted_state_key}",
        ).status_code
        == 204
    )

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        source_scenario = _get_scenario(session, organisation, source_scenario_key)
        first_state = _get_org_state(session, source_scenario, first_state_key)
        boundary_state = _get_org_state(
            session,
            source_scenario,
            boundary_state_key,
        )
        node_type = session.scalar(
            select(NodeType)
            .where(NodeType.node_type_key == "nt_person")
            .order_by(NodeType.metamodel_id.desc()),
        )
        edge_type = session.scalar(
            select(EdgeType)
            .where(EdgeType.edge_type_key == "et_reports_to")
            .order_by(EdgeType.metamodel_id.desc()),
        )
        assert node_type is not None
        assert edge_type is not None
        timeserie = Timeserie(
            scenario_id=source_scenario.scenario_id,
            timeserie_key="source_timeserie",
            name="Source timeserie",
            time_unit="year",
            value_unit="number",
        )
        session.add(timeserie)
        session.flush()
        _add_graph_snapshot(
            session,
            first_state,
            node_type.node_type_id,
            edge_type.edge_type_id,
            graph_name="First graph",
            node_key="node_first",
        )
        _add_graph_snapshot(
            session,
            boundary_state,
            node_type.node_type_id,
            edge_type.edge_type_id,
            graph_name="Boundary graph",
            node_key="node_boundary",
            timeserie_id=timeserie.timeserie_id,
        )
        session.commit()

    copy_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/copy",
        json={
            "sourceScenarioId": source_scenario_key,
            "sourceOrgStateId": boundary_state_key,
            "name": "Copied scenario",
            "description": "Copied",
        },
    )

    assert copy_response.status_code == 201
    copied_payload = cast(dict[str, object], copy_response.json())
    copied_key_value = copied_payload["id"]
    assert isinstance(copied_key_value, str)
    copied_key = copied_key_value
    assert copied_key.startswith("scenario_")
    assert copied_payload == {
        "id": copied_key,
        "name": "Copied scenario",
        "description": "Copied",
        "protected": False,
    }

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        source_scenario = _get_scenario(session, organisation, source_scenario_key)
        copied_scenario = _get_scenario(session, organisation, copied_key)
        copied_org_states = session.scalars(
            select(OrgState)
            .where(
                OrgState.scenario_id == copied_scenario.scenario_id,
                OrgState.deleted_time.is_(None),
            )
            .order_by(OrgState.target_date),
        ).all()
        copied_names = [org_state.name for org_state in copied_org_states]

        assert copied_scenario.source_scenario_id == source_scenario.scenario_id
        assert copied_scenario.protected is False
        assert copied_names == ["First state", "Boundary state"]
        copied_boundary_state = copied_org_states[1]
        assert copied_scenario.initial_state_id == copied_boundary_state.org_state_id

        source_names = [
            org_state.name
            for org_state in session.scalars(
                select(OrgState)
                .where(
                    OrgState.scenario_id == source_scenario.scenario_id,
                    OrgState.deleted_time.is_(None),
                )
                .order_by(OrgState.target_date),
            ).all()
        ]
        assert source_names == ["First state", "Boundary state", "Later state"]

        copied_graphs = session.scalars(
            select(Graph)
            .where(
                Graph.org_state_id.in_(
                    [org_state.org_state_id for org_state in copied_org_states],
                ),
                Graph.deleted_time.is_(None),
            )
            .order_by(Graph.name),
        ).all()
        assert [graph.name for graph in copied_graphs] == [
            "Boundary graph",
            "First graph",
        ]

        copied_boundary_graph = next(
            graph for graph in copied_graphs if graph.name == "Boundary graph"
        )
        copied_node = session.scalar(
            select(GraphNode).where(
                GraphNode.graph_id == copied_boundary_graph.graph_id,
            ),
        )
        copied_edge = session.scalar(
            select(GraphEdge).where(
                GraphEdge.graph_id == copied_boundary_graph.graph_id,
            ),
        )
        assert copied_node is not None
        assert copied_node.node_key == "node_boundary"
        assert copied_node.attributes == {"name": "node_boundary"}
        assert copied_node.timeserie_id is None
        assert copied_node.timeserie_secondary_id is None
        assert copied_edge is not None
        assert copied_edge.edge_key == "edge_node_boundary"
        assert copied_edge.attributes == {"weight": 1}


def test_scenario_copy_allows_protected_source_scenarios(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)

    copy_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/copy",
        json={
            "sourceScenarioId": "reality",
            "sourceOrgStateId": "initial_state",
            "name": "Reality copy",
            "description": "Editable copy",
        },
    )

    assert copy_response.status_code == 201
    copied_key_value = cast(dict[str, object], copy_response.json())["id"]
    assert isinstance(copied_key_value, str)
    copied_key = copied_key_value

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        source_scenario = _get_scenario(session, organisation, "reality")
        copied_scenario = _get_scenario(session, organisation, copied_key)

        assert source_scenario.protected is True
        assert copied_scenario.source_scenario_id == source_scenario.scenario_id
        assert copied_scenario.protected is False


def test_scenario_copy_returns_404_for_missing_source_resources(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)

    missing_scenario_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/copy",
        json={
            "sourceScenarioId": "missing",
            "sourceOrgStateId": "initial_state",
            "name": "Copy",
        },
    )
    assert missing_scenario_response.status_code == 404

    missing_org_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/copy",
        json={
            "sourceScenarioId": "reality",
            "sourceOrgStateId": "missing",
            "name": "Copy",
        },
    )
    assert missing_org_state_response.status_code == 404


def test_scenario_copy_requires_source_org_state_to_belong_to_source_scenario(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    other_scenario_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "Other"},
    )
    assert other_scenario_response.status_code == 201
    other_scenario_key = other_scenario_response.json()["id"]
    other_org_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/"
        f"{other_scenario_key}/org-states",
        json={"name": "Other state", "targetDate": "2031-01-01"},
    )
    assert other_org_state_response.status_code == 201

    response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/copy",
        json={
            "sourceScenarioId": "reality",
            "sourceOrgStateId": other_org_state_response.json()["id"],
            "name": "Invalid copy",
        },
    )

    assert response.status_code == 404


def test_org_state_crud_uses_stable_keys_and_excludes_soft_deleted_rows(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)

    create_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
        json={
            "name": "  Launch state  ",
            "description": "Launch",
            "targetDate": "2030-01-01",
        },
    )
    assert create_response.status_code == 201
    created_org_state = create_response.json()
    assert created_org_state["id"].startswith("org_state_")
    assert created_org_state == {
        "id": created_org_state["id"],
        "name": "Launch state",
        "description": "Launch",
        "targetDate": "2030-01-01",
    }

    org_state_key = created_org_state["id"]
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            f"org-states/{org_state_key}",
        ).json()
        == created_org_state
    )
    assert created_org_state in client.get(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
    ).json()

    patch_response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        f"org-states/{org_state_key}",
        json={
            "name": "Updated launch",
            "description": "Updated",
            "targetDate": "2030-02-01",
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": org_state_key,
        "name": "Updated launch",
        "description": "Updated",
        "targetDate": "2030-02-01",
    }

    delete_response = client.delete(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        f"org-states/{org_state_key}",
    )
    assert delete_response.status_code == 204
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            f"org-states/{org_state_key}",
        ).status_code
        == 404
    )
    listed_ids = [
        item["id"]
        for item in client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
        ).json()
    ]
    assert org_state_key not in listed_ids


def test_org_state_create_and_patch_validate_blank_names(client: TestClient) -> None:
    organisation_key = _create_organisation(client)

    create_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
        json={"name": "   ", "targetDate": "2030-01-01"},
    )
    assert create_response.status_code == 422

    missing_target_date_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
        json={"name": "Missing target date"},
    )
    assert missing_target_date_response.status_code == 422

    patch_response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        "org-states/initial_state",
        json={"name": "   "},
    )
    assert patch_response.status_code == 422

    null_target_date_response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        "org-states/initial_state",
        json={"targetDate": None},
    )
    assert null_target_date_response.status_code == 422


def test_org_state_duplicate_active_target_date_returns_409_and_deleted_date_reuses(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)

    duplicate_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
        json={"name": "Duplicate date", "targetDate": "2020-01-01"},
    )
    assert duplicate_response.status_code == 409

    assert (
        client.delete(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            "org-states/initial_state",
        ).status_code
        == 204
    )
    reused_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
        json={"name": "Reused date", "targetDate": "2020-01-01"},
    )
    assert reused_response.status_code == 201


def test_org_state_delete_clears_scenario_initial_state(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)

    response = client.delete(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        "org-states/initial_state",
    )
    assert response.status_code == 204

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, "reality")
        assert scenario.initial_state_id is None


def test_clean_org_states_service_soft_deletes_active_states_and_clears_initial_state(
    client: TestClient,
    session_factory: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    organisation_key = _create_organisation(client)
    scenario_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "Cleanup scenario", "description": "Cleanup"},
    )
    assert scenario_response.status_code == 201
    scenario_key = cast(str, scenario_response.json()["id"])

    first_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/"
        "org-states",
        json={"name": "First state", "targetDate": "2032-01-01"},
    )
    second_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/"
        "org-states",
        json={"name": "Second state", "targetDate": "2032-02-01"},
    )
    deleted_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/"
        "org-states",
        json={"name": "Deleted state", "targetDate": "2032-03-01"},
    )
    assert first_state_response.status_code == 201
    assert second_state_response.status_code == 201
    assert deleted_state_response.status_code == 201

    first_state_key = cast(str, first_state_response.json()["id"])
    second_state_key = cast(str, second_state_response.json()["id"])
    deleted_state_key = cast(str, deleted_state_response.json()["id"])

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, scenario_key)
        first_state = _get_org_state(session, scenario, first_state_key)
        second_state = _get_org_state(session, scenario, second_state_key)
        deleted_state = _get_org_state(session, scenario, deleted_state_key)
        scenario.initial_state_id = first_state.org_state_id
        node_type = session.scalar(
            select(NodeType)
            .where(NodeType.node_type_key == "nt_person")
            .order_by(NodeType.metamodel_id.desc()),
        )
        edge_type = session.scalar(
            select(EdgeType)
            .where(EdgeType.edge_type_key == "et_reports_to")
            .order_by(EdgeType.metamodel_id.desc()),
        )
        assert node_type is not None
        assert edge_type is not None
        _add_graph_snapshot(
            session,
            first_state,
            node_type.node_type_id,
            edge_type.edge_type_id,
            graph_name="First cleanup graph",
            node_key="node_cleanup_first",
        )
        _add_graph_snapshot(
            session,
            second_state,
            node_type.node_type_id,
            edge_type.edge_type_id,
            graph_name="Second cleanup graph",
            node_key="node_cleanup_second",
        )
        _add_graph_snapshot(
            session,
            deleted_state,
            node_type.node_type_id,
            edge_type.edge_type_id,
            graph_name="Deleted cleanup graph",
            node_key="node_cleanup_deleted",
        )
        session.commit()

    deleted_response = client.delete(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/"
        f"org-states/{deleted_state_key}",
    )
    assert deleted_response.status_code == 204

    with caplog.at_level(logging.INFO, logger=org_states_service.__name__):
        with session_factory() as session:
            cleaned_count = org_states_service.clean_org_states(
                session,
                organisation_key,
                scenario_key,
            )

    assert cleaned_count == 2
    assert (
        "Cleaned 2 organisation states "
        f"for organisation_key={organisation_key} scenario_key={scenario_key}"
        in caplog.text
    )

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, scenario_key)
        cleaned_first_state = _get_org_state_including_deleted(
            session,
            scenario,
            first_state_key,
        )
        cleaned_second_state = _get_org_state_including_deleted(
            session,
            scenario,
            second_state_key,
        )
        previously_deleted_state = _get_org_state_including_deleted(
            session,
            scenario,
            deleted_state_key,
        )
        active_org_states = session.scalars(
            select(OrgState).where(
                OrgState.scenario_id == scenario.scenario_id,
                OrgState.deleted_time.is_(None),
            ),
        ).all()
        cleaned_graphs = session.scalars(
            select(Graph)
            .where(
                Graph.org_state_id.in_(
                    [
                        cleaned_first_state.org_state_id,
                        cleaned_second_state.org_state_id,
                    ],
                ),
            )
            .order_by(Graph.name),
        ).all()
        deleted_graph = session.scalar(
            select(Graph).where(
                Graph.org_state_id == previously_deleted_state.org_state_id,
            ),
        )

        assert scenario.initial_state_id is None
        assert cleaned_first_state.deleted_time is not None
        assert cleaned_second_state.deleted_time is not None
        assert previously_deleted_state.deleted_time is not None
        assert active_org_states == []
        assert [graph.deleted_time is not None for graph in cleaned_graphs] == [
            True,
            True,
        ]
        assert deleted_graph is not None
        assert deleted_graph.deleted_time is not None


def test_clean_org_states_service_returns_zero_when_no_active_states(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    scenario_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "Empty cleanup scenario"},
    )
    assert scenario_response.status_code == 201
    scenario_key = cast(str, scenario_response.json()["id"])

    with session_factory() as session:
        cleaned_count = org_states_service.clean_org_states(
            session,
            organisation_key,
            scenario_key,
        )

    assert cleaned_count == 0


def test_org_states_clean_endpoint_returns_404_for_missing_resources(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)

    missing_org_response = client.post(
        "/api/v1/organisations/missing/scenarios/reality/org-states/clean",
    )
    assert missing_org_response.status_code == 404

    missing_scenario_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/missing/org-states/clean",
    )
    assert missing_scenario_response.status_code == 404


def test_protected_scenario_clean_returns_409(client: TestClient) -> None:
    organisation_key = _create_organisation(client)

    response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states/clean",
    )

    assert response.status_code == 409


def test_org_states_clean_endpoint_returns_count_and_refreshable_state(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    scenario_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "Endpoint cleanup scenario"},
    )
    assert scenario_response.status_code == 201
    scenario_key = cast(str, scenario_response.json()["id"])

    first_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/"
        "org-states",
        json={"name": "State one", "targetDate": "2033-01-01"},
    )
    second_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/"
        "org-states",
        json={"name": "State two", "targetDate": "2033-02-01"},
    )
    assert first_state_response.status_code == 201
    assert second_state_response.status_code == 201

    first_state_key = cast(str, first_state_response.json()["id"])

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, scenario_key)
        first_state = _get_org_state(session, scenario, first_state_key)
        scenario.initial_state_id = first_state.org_state_id
        session.commit()

    response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/clean",
    )

    assert response.status_code == 200
    assert response.json() == {"cleaned": 2}
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states",
        ).json()
        == []
    )

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, scenario_key)
        deleted_org_states = session.scalars(
            select(OrgState).where(OrgState.scenario_id == scenario.scenario_id),
        ).all()

        assert scenario.initial_state_id is None
        assert len(deleted_org_states) == 2
        assert all(
            org_state.deleted_time is not None for org_state in deleted_org_states
        )


def test_scenario_soft_delete_propagates_to_active_owned_rows(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    scenario_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "Propagation", "description": "Checks propagation"},
    )
    assert scenario_response.status_code == 201
    scenario_key_value = cast(dict[str, object], scenario_response.json())["id"]
    assert isinstance(scenario_key_value, str)
    scenario_key = scenario_key_value
    org_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/"
        "org-states",
        json={"name": "Propagation state", "targetDate": "2035-01-01"},
    )
    assert org_state_response.status_code == 201
    org_state_key_value = cast(dict[str, object], org_state_response.json())["id"]
    assert isinstance(org_state_key_value, str)
    org_state_key = org_state_key_value

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, scenario_key)
        org_state = _get_org_state(session, scenario, org_state_key)

        event = Event(
            scenario_id=scenario.scenario_id,
            event_key="event_1",
            name="Event",
            target_date=date(2035, 1, 1),
        )
        timeserie = Timeserie(
            scenario_id=scenario.scenario_id,
            timeserie_key="timeserie_1",
            name="Timeserie",
            time_unit="year",
            value_unit="number",
        )
        graph = Graph(
            org_state_id=org_state.org_state_id,
            name="Graph",
        )
        session.add_all([event, timeserie, graph])
        session.flush()
        node_type = session.scalar(
            select(NodeType)
            .where(NodeType.node_type_key == "nt_person")
            .order_by(NodeType.metamodel_id.desc()),
        )
        edge_type = session.scalar(
            select(EdgeType)
            .where(EdgeType.edge_type_key == "et_reports_to")
            .order_by(EdgeType.metamodel_id.desc()),
        )
        assert node_type is not None
        assert edge_type is not None
        graph_node = GraphNode(
            graph_id=graph.graph_id,
            node_key="node_1",
            node_type_id=node_type.node_type_id,
            attributes={"name": "Node"},
        )
        session.add(graph_node)
        session.flush()
        graph_edge = GraphEdge(
            graph_id=graph.graph_id,
            edge_key="edge_1",
            edge_type_id=edge_type.edge_type_id,
            source_graph_node_id=graph_node.graph_node_id,
            target_graph_node_id=graph_node.graph_node_id,
            attributes={},
        )
        timeserie_value = TimeserieValue(
            timeserie_id=timeserie.timeserie_id,
            date=date(2035, 1, 1),
            value={"value": 42},
        )
        session.add_all([graph_edge, timeserie_value])
        session.commit()

    delete_response = client.delete(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}",
    )
    assert delete_response.status_code == 204

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario_including_deleted(session, organisation, scenario_key)
        org_state = _get_org_state_including_deleted(session, scenario, org_state_key)
        event = session.scalar(
            select(Event).where(Event.scenario_id == scenario.scenario_id),
        )
        timeserie = session.scalar(
            select(Timeserie).where(Timeserie.scenario_id == scenario.scenario_id),
        )
        assert timeserie is not None
        timeserie_value = session.scalar(
            select(TimeserieValue).where(
                TimeserieValue.timeserie_id == timeserie.timeserie_id,
            ),
        )
        graph = session.scalar(
            select(Graph).where(Graph.org_state_id == org_state.org_state_id),
        )
        assert graph is not None
        graph_node = session.scalar(
            select(GraphNode).where(GraphNode.graph_id == graph.graph_id),
        )
        graph_edge = session.scalar(
            select(GraphEdge).where(GraphEdge.graph_id == graph.graph_id),
        )

        assert scenario.deleted_time is not None
        assert org_state.deleted_time is not None
        assert event is not None
        assert event.deleted_time is not None
        assert timeserie.deleted_time is not None
        assert timeserie_value is not None
        assert timeserie_value.deleted_time is not None
        assert graph.deleted_time is not None
        assert graph_node is not None
        assert graph_node.deleted_time is not None
        assert graph_edge is not None
        assert graph_edge.deleted_time is not None


def _create_organisation(client: TestClient, name: str = "Acme Corp") -> str:
    response = client.post("/api/v1/organisations", json={"name": name})
    assert response.status_code == 201
    organisation_key = response.json()["id"]
    assert isinstance(organisation_key, str)
    return organisation_key


def _get_organisation(session: Session, organisation_key: str) -> Organisation:
    organisation = session.scalar(
        select(Organisation).where(Organisation.organisation_key == organisation_key),
    )
    assert organisation is not None
    return organisation


def _get_scenario(
    session: Session,
    organisation: Organisation,
    scenario_key: str,
) -> Scenario:
    scenario = session.scalar(
        select(Scenario).where(
            Scenario.organisation_id == organisation.organisation_id,
            Scenario.scenario_key == scenario_key,
            Scenario.deleted_time.is_(None),
        ),
    )
    assert scenario is not None
    return scenario


def _get_scenario_including_deleted(
    session: Session,
    organisation: Organisation,
    scenario_key: str,
) -> Scenario:
    scenario = session.scalar(
        select(Scenario).where(
            Scenario.organisation_id == organisation.organisation_id,
            Scenario.scenario_key == scenario_key,
        ),
    )
    assert scenario is not None
    return scenario


def _get_org_state(
    session: Session,
    scenario: Scenario,
    org_state_key: str,
) -> OrgState:
    org_state = session.scalar(
        select(OrgState).where(
            OrgState.scenario_id == scenario.scenario_id,
            OrgState.org_state_key == org_state_key,
            OrgState.deleted_time.is_(None),
        ),
    )
    assert org_state is not None
    return org_state


def _get_org_state_including_deleted(
    session: Session,
    scenario: Scenario,
    org_state_key: str,
) -> OrgState:
    org_state = session.scalar(
        select(OrgState).where(
            OrgState.scenario_id == scenario.scenario_id,
            OrgState.org_state_key == org_state_key,
        ),
    )
    assert org_state is not None
    return org_state


def _add_graph_snapshot(
    session: Session,
    org_state: OrgState,
    node_type_id: int,
    edge_type_id: int,
    *,
    graph_name: str,
    node_key: str,
    timeserie_id: int | None = None,
) -> None:
    graph = Graph(
        org_state_id=org_state.org_state_id,
        name=graph_name,
    )
    session.add(graph)
    session.flush()
    graph_node = GraphNode(
        graph_id=graph.graph_id,
        node_key=node_key,
        node_type_id=node_type_id,
        create_date=org_state.target_date,
        attributes={"name": node_key},
        timeserie_id=timeserie_id,
        timeserie_secondary_id=timeserie_id,
    )
    session.add(graph_node)
    session.flush()
    session.add(
        GraphEdge(
            graph_id=graph.graph_id,
            edge_key=f"edge_{node_key}",
            edge_type_id=edge_type_id,
            source_graph_node_id=graph_node.graph_node_id,
            target_graph_node_id=graph_node.graph_node_id,
            create_date=org_state.target_date,
            attributes={"weight": 1},
        ),
    )
