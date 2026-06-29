from collections.abc import Iterator
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_states.models import OrgState, Scenario
from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
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
