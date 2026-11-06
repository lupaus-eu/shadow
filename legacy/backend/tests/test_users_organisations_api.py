import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import cast

import pytest
from auth_helpers import TEST_ACTOR_USER_ID, authenticate_test_client
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import (
    Event,
    OrgState,
    Scenario,
    Timeserie,
    TimeserieValue,
)
from app.api.v1.org_states.schemas import TimeserieCreateRequest
from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
    GraphEdge,
    GraphNode,
    Metamodel,
    NodeType,
    TypeAttribute,
)
from app.api.v1.organisations.models import Organisation
from app.api.v1.users.models import User
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
        authenticate_test_client(test_client, session_factory)
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
        json={
            "name": "  Ada Lovelace  ",
            "email": "  Ada.Lovelace@Example.COM  ",
            "role": "admin",
        },
    )
    assert create_response.status_code == 201
    created_user = create_response.json()
    assert created_user == {
        "id": 1,
        "name": "Ada Lovelace",
        "email": "Ada.Lovelace@Example.COM",
        "role": "admin",
    }

    user_id = created_user["id"]
    assert client.get(f"/api/v1/users/{user_id}").json() == created_user
    assert client.get("/api/v1/users").json() == [
        {
            "id": TEST_ACTOR_USER_ID,
            "name": "Test Admin",
            "email": "test-0@example.test",
            "role": "admin",
        },
        created_user,
    ]

    patch_response = client.patch(
        f"/api/v1/users/{user_id}",
        json={
            "name": "Grace Hopper",
            "email": "grace@example.local",
            "role": "consultant",
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": user_id,
        "name": "Grace Hopper",
        "email": "grace@example.local",
        "role": "consultant",
    }

    delete_response = client.delete(f"/api/v1/users/{user_id}")
    assert delete_response.status_code == 204
    assert [user["id"] for user in client.get("/api/v1/users").json()] == [
        TEST_ACTOR_USER_ID
    ]
    assert client.get(f"/api/v1/users/{user_id}").status_code == 404


def test_platform_accounts_are_invisible_to_the_users_api(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        operator = User(
            name="Operator",
            email="operator@example.test",
            role="admin",
            account_class="platform",
        )
        session.add(operator)
        session.commit()
        operator_id = operator.user_id

    listed = client.get("/api/v1/users").json()
    assert "operator@example.test" not in {user["email"] for user in listed}
    path = f"/api/v1/users/{operator_id}"
    assert client.get(path).status_code == 404
    assert client.patch(path, json={"name": "Renamed"}).status_code == 404
    assert client.patch(path, json={"email": "mine@example.test"}).status_code == 404
    assert client.delete(path).status_code == 404
    assert client.post(f"{path}/sessions/revoke").status_code == 404
    with session_factory() as session:
        stored = session.get(User, operator_id)
        assert stored is not None
        assert (stored.name, stored.email, stored.deleted_time) == (
            "Operator",
            "operator@example.test",
            None,
        )


def test_user_create_rejects_invalid_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/users",
        json={"name": "Ada Lovelace", "email": "ada@example.local", "role": "owner"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Ada Lovelace", "role": "admin"},
        {"name": "Ada Lovelace", "email": None, "role": "admin"},
        {"name": "Ada Lovelace", "email": "   ", "role": "admin"},
    ],
)
def test_user_create_rejects_missing_null_and_blank_email(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    assert client.post("/api/v1/users", json=payload).status_code == 422


@pytest.mark.parametrize("email", [None, "   "])
def test_user_patch_rejects_null_and_blank_email(
    client: TestClient,
    email: object,
) -> None:
    created = client.post(
        "/api/v1/users",
        json={"name": "Ada", "email": "ada@example.local", "role": "admin"},
    ).json()

    response = client.patch(
        f"/api/v1/users/{created['id']}",
        json={"email": email},
    )

    assert response.status_code == 422


def test_duplicate_active_user_email_returns_409(client: TestClient) -> None:
    first = client.post(
        "/api/v1/users",
        json={"name": "Ada", "email": "Ada@Example.Local", "role": "admin"},
    )
    assert first.status_code == 201

    duplicate = client.post(
        "/api/v1/users",
        json={"name": "Grace", "email": "ada@example.local", "role": "consultant"},
    )

    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "detail": "An active user with this email already exists."
    }


def test_user_patch_rejects_duplicate_active_email(client: TestClient) -> None:
    first = client.post(
        "/api/v1/users",
        json={"name": "Ada", "email": "ada@example.local", "role": "admin"},
    ).json()
    second = client.post(
        "/api/v1/users",
        json={"name": "Grace", "email": "grace@example.local", "role": "consultant"},
    ).json()

    response = client.patch(
        f"/api/v1/users/{second['id']}",
        json={"email": "ADA@example.local"},
    )

    assert response.status_code == 409
    assert client.get(f"/api/v1/users/{first['id']}").status_code == 200


def test_soft_deleted_user_email_can_be_reused(client: TestClient) -> None:
    first = client.post(
        "/api/v1/users",
        json={"name": "Ada", "email": "Ada@Example.Local", "role": "admin"},
    ).json()
    assert client.delete(f"/api/v1/users/{first['id']}").status_code == 204

    replacement = client.post(
        "/api/v1/users",
        json={"name": "New Ada", "email": "ada@example.local", "role": "consultant"},
    )

    assert replacement.status_code == 201


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
    assert (
        created_scenario
        in client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios",
        ).json()
    )

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


def test_scenario_copy_copies_selected_org_state_and_graph_snapshot(
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
        primary_timeserie = Timeserie(
            scenario_id=source_scenario.scenario_id,
            timeserie_key="source_timeserie",
            name="Source timeserie",
            short_name="source_metric",
            description="Primary source metric",
            unit="EUR",
            time_unit="month",
            value_unit="number",
        )
        secondary_timeserie = Timeserie(
            scenario_id=source_scenario.scenario_id,
            timeserie_key="secondary_timeserie",
            name="Secondary timeserie",
            description="Secondary source metric",
            unit="flag",
            time_unit="week",
            value_unit="boolean",
        )
        string_timeserie = Timeserie(
            scenario_id=source_scenario.scenario_id,
            timeserie_key="status_timeserie",
            name="Status timeserie",
            description="String source metric",
            unit="",
            time_unit="day",
            value_unit="string",
        )
        empty_timeserie = Timeserie(
            scenario_id=source_scenario.scenario_id,
            timeserie_key="empty_timeserie",
            name="Empty timeserie",
            time_unit="year",
            value_unit="number",
        )
        future_primary_timeserie = Timeserie(
            scenario_id=source_scenario.scenario_id,
            timeserie_key="future_primary_timeserie",
            name="Future primary timeserie",
            time_unit="month",
            value_unit="number",
        )
        future_secondary_timeserie = Timeserie(
            scenario_id=source_scenario.scenario_id,
            timeserie_key="future_secondary_timeserie",
            name="Future secondary timeserie",
            time_unit="month",
            value_unit="number",
        )
        deleted_timeserie = Timeserie(
            scenario_id=source_scenario.scenario_id,
            timeserie_key="deleted_timeserie",
            name="Deleted timeserie",
            time_unit="year",
            value_unit="number",
            deleted_by=TEST_ACTOR_USER_ID,
            deleted_time=datetime.now(UTC),
        )
        session.add_all(
            [
                primary_timeserie,
                secondary_timeserie,
                string_timeserie,
                empty_timeserie,
                future_primary_timeserie,
                future_secondary_timeserie,
                deleted_timeserie,
            ],
        )
        session.flush()
        session.add_all(
            [
                Event(
                    scenario_id=source_scenario.scenario_id,
                    event_key="before_event",
                    name="Before event",
                    target_date=date(2030, 1, 1),
                    version=3,
                    event_details="Before boundary",
                ),
                Event(
                    scenario_id=source_scenario.scenario_id,
                    event_key="boundary_event",
                    name="Boundary event",
                    target_date=date(2030, 2, 1),
                    version=4,
                    event_details="On boundary",
                ),
                Event(
                    scenario_id=source_scenario.scenario_id,
                    event_key="later_event",
                    name="Later event",
                    target_date=date(2030, 3, 1),
                    event_details="After boundary",
                ),
                Event(
                    scenario_id=source_scenario.scenario_id,
                    event_key="deleted_event",
                    name="Deleted event",
                    target_date=date(2030, 1, 15),
                    event_details="Soft deleted",
                    deleted_by=TEST_ACTOR_USER_ID,
                    deleted_time=datetime.now(UTC),
                ),
                TimeserieValue(
                    timeserie_id=primary_timeserie.timeserie_id,
                    date=date(2029, 12, 1),
                    value={"value": 100},
                ),
                TimeserieValue(
                    timeserie_id=primary_timeserie.timeserie_id,
                    date=date(2030, 2, 1),
                    value={"value": 200},
                ),
                TimeserieValue(
                    timeserie_id=primary_timeserie.timeserie_id,
                    date=date(2030, 3, 1),
                    value={"value": 300},
                ),
                TimeserieValue(
                    timeserie_id=primary_timeserie.timeserie_id,
                    date=date(2030, 1, 1),
                    value={"value": 50},
                    deleted_by=TEST_ACTOR_USER_ID,
                    deleted_time=datetime.now(UTC),
                ),
                TimeserieValue(
                    timeserie_id=secondary_timeserie.timeserie_id,
                    date=date(2030, 1, 29),
                    value={"value": False},
                ),
                TimeserieValue(
                    timeserie_id=string_timeserie.timeserie_id,
                    date=date(2030, 1, 30),
                    value={"value": "ready"},
                ),
                TimeserieValue(
                    timeserie_id=future_primary_timeserie.timeserie_id,
                    date=date(2030, 3, 1),
                    value={"value": 400},
                ),
                TimeserieValue(
                    timeserie_id=future_secondary_timeserie.timeserie_id,
                    date=date(2030, 3, 1),
                    value={"value": 500},
                ),
            ],
        )
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
            timeserie_id=primary_timeserie.timeserie_id,
            timeserie_secondary_id=secondary_timeserie.timeserie_id,
        )
        session.add_all(
            [
                GraphNode(
                    scenario_id=source_scenario.scenario_id,
                    node_key="node_future_primary",
                    name="Future primary graph",
                    node_type_id=node_type.node_type_id,
                    create_date=date(2030, 3, 1),
                    timeserie_id=future_primary_timeserie.timeserie_id,
                    timeserie_secondary_id=future_secondary_timeserie.timeserie_id,
                ),
            ],
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
    copied_timeseries_response = client.get(
        f"/api/v1/organisations/{organisation_key}/scenarios/{copied_key}/timeseries",
    )
    assert copied_timeseries_response.status_code == 200
    assert {timeserie["id"] for timeserie in copied_timeseries_response.json()} == {
        "empty_timeserie",
        "future_primary_timeserie",
        "future_secondary_timeserie",
        "secondary_timeserie",
        "source_timeserie",
        "status_timeserie",
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
        assert copied_names == ["Boundary state"]
        copied_boundary_state = copied_org_states[0]
        assert copied_boundary_state.org_state_key != boundary_state_key
        assert copied_boundary_state.target_date.isoformat() == "2030-02-01"
        assert copied_scenario.initial_state_id == copied_boundary_state.org_state_id

        copied_events = session.scalars(
            select(Event)
            .where(
                Event.scenario_id == copied_scenario.scenario_id,
                Event.deleted_time.is_(None),
            )
            .order_by(Event.target_date, Event.event_id),
        ).all()
        assert [event.event_key for event in copied_events] == [
            "before_event",
            "boundary_event",
        ]
        copied_boundary_event = next(
            event for event in copied_events if event.event_key == "boundary_event"
        )
        source_boundary_event = _get_event_including_deleted(
            session,
            source_scenario,
            "boundary_event",
        )
        assert copied_boundary_event.event_id != source_boundary_event.event_id
        assert (
            copied_boundary_event.name,
            copied_boundary_event.target_date,
            copied_boundary_event.version,
            copied_boundary_event.event_details,
            copied_boundary_event.created_by,
        ) == (
            "Boundary event",
            date(2030, 2, 1),
            4,
            "On boundary",
            TEST_ACTOR_USER_ID,
        )

        copied_timeseries = {
            timeserie.timeserie_key: timeserie
            for timeserie in session.scalars(
                select(Timeserie)
                .where(
                    Timeserie.scenario_id == copied_scenario.scenario_id,
                    Timeserie.deleted_time.is_(None),
                )
                .order_by(Timeserie.timeserie_key, Timeserie.timeserie_id),
            ).all()
        }
        assert set(copied_timeseries) == {
            "empty_timeserie",
            "future_primary_timeserie",
            "future_secondary_timeserie",
            "secondary_timeserie",
            "source_timeserie",
            "status_timeserie",
        }
        copied_primary_timeserie = copied_timeseries["source_timeserie"]
        copied_secondary_timeserie = copied_timeseries["secondary_timeserie"]
        source_primary_timeserie = session.scalar(
            select(Timeserie).where(
                Timeserie.scenario_id == source_scenario.scenario_id,
                Timeserie.timeserie_key == "source_timeserie",
            ),
        )
        assert source_primary_timeserie is not None
        assert (
            copied_primary_timeserie.timeserie_id
            != source_primary_timeserie.timeserie_id
        )
        assert (
            copied_primary_timeserie.name,
            copied_primary_timeserie.short_name,
            copied_primary_timeserie.description,
            copied_primary_timeserie.unit,
            copied_primary_timeserie.time_unit,
            copied_primary_timeserie.value_unit,
            copied_primary_timeserie.created_by,
        ) == (
            "Source timeserie",
            "source_metric",
            "Primary source metric",
            "EUR",
            "month",
            "number",
            TEST_ACTOR_USER_ID,
        )
        copied_values = {
            timeserie_key: [
                (value.date, value.value, value.created_by)
                for value in session.scalars(
                    select(TimeserieValue)
                    .where(
                        TimeserieValue.timeserie_id == timeserie.timeserie_id,
                        TimeserieValue.deleted_time.is_(None),
                    )
                    .order_by(TimeserieValue.date, TimeserieValue.timeserie_value_id),
                ).all()
            ]
            for timeserie_key, timeserie in copied_timeseries.items()
        }
        assert copied_values == {
            "empty_timeserie": [],
            "future_primary_timeserie": [],
            "future_secondary_timeserie": [],
            "secondary_timeserie": [
                (date(2030, 1, 29), {"value": False}, TEST_ACTOR_USER_ID),
            ],
            "source_timeserie": [
                (date(2029, 12, 1), {"value": 100}, TEST_ACTOR_USER_ID),
                (date(2030, 2, 1), {"value": 200}, TEST_ACTOR_USER_ID),
            ],
            "status_timeserie": [
                (date(2030, 1, 30), {"value": "ready"}, TEST_ACTOR_USER_ID),
            ],
        }

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

        copied_nodes = session.scalars(
            select(GraphNode)
            .where(
                GraphNode.scenario_id == copied_scenario.scenario_id,
                GraphNode.deleted_time.is_(None),
            )
            .order_by(GraphNode.create_date, GraphNode.node_key),
        ).all()
        assert [node.node_key for node in copied_nodes] == [
            "node_first",
            "node_boundary",
        ]

        copied_boundary_node = next(
            node for node in copied_nodes if node.node_key == "node_boundary"
        )
        copied_edge = session.scalar(
            select(GraphEdge).where(
                GraphEdge.scenario_id == copied_scenario.scenario_id,
                GraphEdge.edge_key == "edge_node_boundary",
            ),
        )
        assert copied_boundary_node.attributes == {"name": "node_boundary"}
        assert (
            copied_boundary_node.timeserie_id == copied_primary_timeserie.timeserie_id
        )
        assert (
            copied_boundary_node.timeserie_secondary_id
            == copied_secondary_timeserie.timeserie_id
        )
        assert copied_edge is not None
        assert copied_edge.source_graph_node_id == copied_boundary_node.graph_node_id
        assert copied_edge.target_graph_node_id == copied_boundary_node.graph_node_id
        assert copied_edge.attributes == {"weight": 1}

        copied_boundary_event.name = "Copied event only"
        copied_primary_value = session.scalar(
            select(TimeserieValue).where(
                TimeserieValue.timeserie_id == copied_primary_timeserie.timeserie_id,
                TimeserieValue.date == date(2029, 12, 1),
            ),
        )
        assert copied_primary_value is not None
        copied_primary_value.value = {"value": 999}
        session.commit()

    assert (
        client.delete(
            f"/api/v1/organisations/{organisation_key}/scenarios/"
            f"{copied_key}/timeseries/source_timeserie",
        ).status_code
        == 204
    )

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        source_scenario = _get_scenario(session, organisation, source_scenario_key)
        copied_scenario = _get_scenario(session, organisation, copied_key)
        source_boundary_event = _get_event_including_deleted(
            session,
            source_scenario,
            "boundary_event",
        )
        source_primary_timeserie = session.scalar(
            select(Timeserie).where(
                Timeserie.scenario_id == source_scenario.scenario_id,
                Timeserie.timeserie_key == "source_timeserie",
            ),
        )
        copied_primary_timeserie = session.scalar(
            select(Timeserie).where(
                Timeserie.scenario_id == copied_scenario.scenario_id,
                Timeserie.timeserie_key == "source_timeserie",
            ),
        )
        assert source_primary_timeserie is not None
        assert copied_primary_timeserie is not None
        source_primary_value = session.scalar(
            select(TimeserieValue)
            .join(Timeserie)
            .where(
                Timeserie.scenario_id == source_scenario.scenario_id,
                Timeserie.timeserie_key == "source_timeserie",
                TimeserieValue.date == date(2029, 12, 1),
            ),
        )
        copied_primary_value = session.scalar(
            select(TimeserieValue).where(
                TimeserieValue.timeserie_id == copied_primary_timeserie.timeserie_id,
                TimeserieValue.date == date(2029, 12, 1),
            ),
        )
        assert source_primary_value is not None
        assert copied_primary_value is not None
        assert (
            copied_primary_value.timeserie_value_id
            != source_primary_value.timeserie_value_id
        )
        assert source_boundary_event.name == "Boundary event"
        assert source_primary_timeserie.deleted_time is None
        assert source_primary_value.value == {"value": 100}
        assert source_primary_value.deleted_time is None
        assert copied_primary_timeserie.deleted_by == TEST_ACTOR_USER_ID
        assert copied_primary_timeserie.deleted_time is not None
        assert copied_primary_value.deleted_by == TEST_ACTOR_USER_ID
        assert copied_primary_value.deleted_time is not None


@pytest.mark.parametrize("name_payload", [{}, {"name": "  "}])
def test_scenario_copy_defaults_blank_or_missing_name(
    client: TestClient,
    name_payload: dict[str, str],
) -> None:
    organisation_key = _create_organisation(client)

    copy_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/copy",
        json={
            "sourceScenarioId": "reality",
            "sourceOrgStateId": "initial_state",
            "description": "Generated name",
            **name_payload,
        },
    )

    assert copy_response.status_code == 201
    copied_payload = cast(dict[str, object], copy_response.json())
    assert copied_payload["name"] == "Fork of Reality"


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
    assert (
        created_org_state
        in client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
        ).json()
    )

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


def test_event_crud_uses_stable_keys_and_excludes_soft_deleted_rows(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)

    create_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/events",
        json={
            "name": "  Market launch  ",
            "targetDate": "2030-01-01",
            "eventDetails": "Initial launch",
        },
    )
    assert create_response.status_code == 201
    created_event = create_response.json()
    assert created_event["id"].startswith("event_")
    assert created_event == {
        "id": created_event["id"],
        "name": "Market launch",
        "targetDate": "2030-01-01",
        "eventDetails": "Initial launch",
    }

    event_key = created_event["id"]
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            f"events/{event_key}",
        ).json()
        == created_event
    )
    assert (
        created_event
        in client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/events",
        ).json()
    )

    patch_response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        f"events/{event_key}",
        json={
            "name": "Updated launch",
            "targetDate": "2030-02-01",
            "eventDetails": "Updated details",
        },
    )
    assert patch_response.status_code == 200
    assert patch_response.json() == {
        "id": event_key,
        "name": "Updated launch",
        "targetDate": "2030-02-01",
        "eventDetails": "Updated details",
    }

    delete_response = client.delete(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        f"events/{event_key}",
    )
    assert delete_response.status_code == 204
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            f"events/{event_key}",
        ).status_code
        == 404
    )
    listed_ids = [
        item["id"]
        for item in client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/events",
        ).json()
    ]
    assert event_key not in listed_ids

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, "reality")
        event = _get_event_including_deleted(session, scenario, event_key)
        assert event.deleted_time is not None


def test_event_endpoints_return_404_for_missing_parents_and_resources(
    client: TestClient,
) -> None:
    assert (
        client.get(
            "/api/v1/organisations/missing/scenarios/reality/events",
        ).status_code
        == 404
    )

    organisation_key = _create_organisation(client)
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/missing/events",
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            "events/missing",
        ).status_code
        == 404
    )


def test_event_create_and_patch_validate_required_fields(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)

    blank_name_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/events",
        json={"name": "   ", "targetDate": "2030-01-01"},
    )
    assert blank_name_response.status_code == 422

    missing_target_date_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/events",
        json={"name": "Missing target date"},
    )
    assert missing_target_date_response.status_code == 422

    create_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/events",
        json={"name": "Launch", "targetDate": "2030-01-01"},
    )
    assert create_response.status_code == 201
    event_key = cast(str, create_response.json()["id"])

    blank_patch_name_response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        f"events/{event_key}",
        json={"name": "   "},
    )
    assert blank_patch_name_response.status_code == 422

    null_target_date_response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
        f"events/{event_key}",
        json={"targetDate": None},
    )
    assert null_target_date_response.status_code == 422


def test_event_duplicate_target_dates_are_allowed_inside_scenario(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    path = f"/api/v1/organisations/{organisation_key}/scenarios/reality/events"

    first_response = client.post(
        path,
        json={"name": "First launch", "targetDate": "2030-01-01"},
    )
    second_response = client.post(
        path,
        json={"name": "Second launch", "targetDate": "2030-01-01"},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    listed_events = client.get(path).json()
    assert [item["targetDate"] for item in listed_events] == [
        "2030-01-01",
        "2030-01-01",
    ]


def test_timeserie_crud_uses_stable_keys_and_validates_units(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    path = f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"

    create_response = client.post(
        path,
        json={
            "id": "revenue",
            "name": "  Revenue  ",
            "shortName": "  revenue_monthly  ",
            "description": "  Monthly revenue  ",
            "unit": "  EUR  ",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json() == {
        "id": "revenue",
        "name": "Revenue",
        "shortName": "revenue_monthly",
        "description": "Monthly revenue",
        "unit": "EUR",
        "timeUnit": "month",
        "valueUnit": "number",
        "values": [],
        "isDerived": False,
        "derivedFormula": None,
        "shortNameEditable": True,
    }
    assert client.get(f"{path}/revenue").json() == create_response.json()
    assert client.get(f"{path}/revenue/exists").json() == {
        "id": "revenue",
        "exists": True,
        "shortName": "revenue_monthly",
        "shortNameEditable": True,
    }
    assert client.get(f"{path}/missing/exists").json() == {
        "id": "missing",
        "exists": False,
        "shortName": "",
        "shortNameEditable": True,
    }
    assert client.get(f"{path}/missing").status_code == 404
    assert (
        client.post(
            path,
            json={
                "id": "revenue",
                "name": "Duplicate",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 409
    )
    duplicate_name_response = client.post(
        path,
        json={
            "id": "revenue_duplicate_name",
            "name": "  revenue  ",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    )
    assert duplicate_name_response.status_code == 409
    assert duplicate_name_response.json() == {
        "detail": "An active timeserie with this name already exists."
    }
    duplicate_short_name_response = client.post(
        path,
        json={
            "id": "revenue_duplicate_short_name",
            "name": "Revenue duplicate",
            "shortName": "revenue_monthly",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    )
    assert duplicate_short_name_response.status_code == 409
    assert (
        client.post(
            path,
            json={
                "id": "bad_unit",
                "name": "Bad unit",
                "timeUnit": "quarter",
                "valueUnit": "number",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            path,
            json={
                "id": "bad_short_name",
                "name": "Bad short name",
                "shortName": "bad-short-name",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            path,
            json={
                "id": "  ",
                "name": "Blank id",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 422
    )


def test_timeserie_name_can_be_reused_in_another_scenario_or_after_soft_delete(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    reality_path = (
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"
    )
    assert (
        client.post(
            reality_path,
            json={
                "id": "revenue",
                "name": "Revenue",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 201
    )

    scenario_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "Forecast"},
    )
    assert scenario_response.status_code == 201
    scenario_key = scenario_response.json()["id"]
    other_scenario_path = (
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries"
    )
    assert (
        client.post(
            other_scenario_path,
            json={
                "id": "revenue",
                "name": " revenue ",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 201
    )

    assert client.delete(f"{reality_path}/revenue").status_code == 204
    assert (
        client.post(
            reality_path,
            json={
                "id": "revenue_replacement",
                "name": "REVENUE",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 201
    )


def test_timeserie_create_maps_database_uniqueness_races_to_conflict(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        organisation = Organisation(organisation_key="acme", name="Acme")
        session.add(organisation)
        session.flush()
        scenario = Scenario(
            organisation_id=organisation.organisation_id,
            scenario_key="reality",
            name="Reality",
        )
        session.add(scenario)
        session.commit()

        def raise_unique_violation() -> None:
            raise IntegrityError("INSERT", {}, Exception("duplicate key"))

        monkeypatch.setattr(session, "commit", raise_unique_violation)

        with pytest.raises(HTTPException) as error:
            org_states_service.create_timeserie(
                session,
                "acme",
                "reality",
                TimeserieCreateRequest(
                    id="revenue",
                    name="Revenue",
                    timeUnit="month",
                    valueUnit="number",
                ),
                TEST_ACTOR_USER_ID,
            )

        assert error.value.status_code == 409
        assert error.value.detail == (
            "An active timeserie with this id, name, or short name already exists."
        )


def test_timeseries_list_returns_sorted_rows_and_active_sorted_values(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    path = f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"
    assert (
        client.post(
            path,
            json={
                "id": "revenue",
                "name": "Revenue",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            path,
            json={
                "id": "capacity",
                "name": "Capacity",
                "timeUnit": "week",
                "valueUnit": "boolean",
            },
        ).status_code
        == 201
    )

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, "reality")
        revenue = session.scalar(
            select(Timeserie).where(
                Timeserie.scenario_id == scenario.scenario_id,
                Timeserie.timeserie_key == "revenue",
            ),
        )
        capacity = session.scalar(
            select(Timeserie).where(
                Timeserie.scenario_id == scenario.scenario_id,
                Timeserie.timeserie_key == "capacity",
            ),
        )
        assert revenue is not None
        assert capacity is not None
        deleted_time = datetime.now(UTC)
        session.add_all(
            [
                TimeserieValue(
                    timeserie_id=revenue.timeserie_id,
                    date=date(2030, 2, 1),
                    value={"value": 2000},
                ),
                TimeserieValue(
                    timeserie_id=revenue.timeserie_id,
                    date=date(2030, 1, 1),
                    value={"value": 1000},
                ),
                TimeserieValue(
                    timeserie_id=revenue.timeserie_id,
                    date=date(2030, 3, 1),
                    value={"value": 3000},
                    deleted_time=deleted_time,
                ),
                TimeserieValue(
                    timeserie_id=capacity.timeserie_id,
                    date=date(2030, 1, 7),
                    value={"value": True},
                ),
            ],
        )
        session.commit()

    list_response = client.get(path)

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == ["capacity", "revenue"]
    assert list_response.json()[0]["values"] == [
        {"date": "2030-01-07", "value": True},
    ]
    assert list_response.json()[1]["values"] == [
        {"date": "2030-01-01", "value": 1000},
        {"date": "2030-02-01", "value": 2000},
    ]
    assert client.get(f"{path}/revenue").json()["values"] == [
        {"date": "2030-01-01", "value": 1000},
        {"date": "2030-02-01", "value": 2000},
    ]


def test_timeseries_list_without_values_returns_same_rows_and_reads_no_values(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    scenario_path = f"/api/v1/organisations/{organisation_key}/scenarios/reality"
    path = f"{scenario_path}/timeseries"
    for timeserie_id, short_name, value_unit, values in (
        ("revenue", "revenue", "number", [100, 200, 300]),
        ("cost", "cost", "number", [40]),
        ("status", "status", "string", ["open"]),
        ("capacity", "capacity", "boolean", [True]),
        ("retired", "retired", "number", [1]),
    ):
        created = client.post(
            path,
            json={
                "id": timeserie_id,
                "name": timeserie_id.title(),
                "shortName": short_name,
                "timeUnit": "month",
                "valueUnit": value_unit,
            },
        )
        assert created.status_code == 201
        replaced = client.patch(
            f"{path}/{timeserie_id}/values",
            json={
                "values": [
                    {"date": f"2030-{month:02d}-01", "value": value}
                    for month, value in enumerate(values, start=1)
                ]
            },
        )
        assert replaced.status_code == 200
    # Replacing revenue's values soft-deletes its third value.
    assert (
        client.patch(
            f"{path}/revenue/values",
            json={
                "values": [
                    {"date": "2030-01-01", "value": 100},
                    {"date": "2030-02-01", "value": 200},
                ]
            },
        ).status_code
        == 200
    )
    assert client.delete(f"{path}/retired").status_code == 204
    derived = client.post(
        f"{scenario_path}/derived-metrics",
        json={"name": "Margin", "unit": "EUR", "formula": "revenue - cost"},
    )
    assert derived.status_code == 201
    derived_id = derived.json()["id"]

    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        *_args: object,
    ) -> None:
        statements.append(statement)

    engine = session_factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        with_values = client.get(path)
        value_statements = [s for s in statements if "timeserie_values" in s]
        statements.clear()
        without_values = client.get(path, params={"includeValues": "false"})
        statements_without_values = list(statements)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    assert with_values.status_code == 200
    assert without_values.status_code == 200
    # The recorder sees the value read when values are requested ...
    assert value_statements
    # ... and none when they are not.
    assert statements_without_values
    assert not [s for s in statements_without_values if "timeserie_values" in s]

    with_values_rows = with_values.json()
    without_values_rows = without_values.json()
    assert [row["id"] for row in without_values_rows] == sorted(
        ["capacity", "cost", derived_id, "revenue", "status"]
    )
    assert [row["id"] for row in without_values_rows] == [
        row["id"] for row in with_values_rows
    ]
    assert all(row["values"] == [] for row in without_values_rows)
    assert [{**row, "values": []} for row in with_values_rows] == without_values_rows
    by_id = {row["id"]: row for row in with_values_rows}
    assert by_id["revenue"]["values"] == [
        {"date": "2030-01-01", "value": 100},
        {"date": "2030-02-01", "value": 200},
    ]
    assert by_id[derived_id]["isDerived"] is True
    assert by_id[derived_id]["values"] == [{"date": "2030-01-01", "value": 60.0}]
    derived_without_values = next(
        row for row in without_values_rows if row["id"] == derived_id
    )
    assert derived_without_values["isDerived"] is True
    assert derived_without_values["derivedFormula"] == "revenue - cost"
    assert by_id["revenue"]["shortNameEditable"] is False


def test_timeseries_list_include_values_defaults_to_true(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    path = f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"
    assert (
        client.post(
            path,
            json={
                "id": "revenue",
                "name": "Revenue",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 201
    )
    assert (
        client.patch(
            f"{path}/revenue/values",
            json={"values": [{"date": "2030-01-01", "value": 1000}]},
        ).status_code
        == 200
    )

    expected_values = [{"date": "2030-01-01", "value": 1000}]
    omitted = client.get(path)
    explicit = client.get(path, params={"includeValues": "true"})
    assert omitted.status_code == 200
    assert explicit.status_code == 200
    assert omitted.json()[0]["values"] == expected_values
    assert explicit.json() == omitted.json()
    assert client.get(path, params={"includeValues": "maybe"}).status_code == 422


def test_timeseries_list_without_values_returns_same_not_found_errors(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    for path in (
        "/api/v1/organisations/missing/scenarios/reality/timeseries",
        f"/api/v1/organisations/{organisation_key}/scenarios/missing/timeseries",
    ):
        with_values = client.get(path)
        without_values = client.get(path, params={"includeValues": "false"})
        assert with_values.status_code == 404
        assert without_values.status_code == 404
        assert without_values.json() == with_values.json()


def test_timeserie_values_replace_number_values_and_soft_delete_omissions(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    path = f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"
    assert (
        client.post(
            path,
            json={
                "id": "revenue",
                "name": "Revenue",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 201
    )

    replace_response = client.patch(
        f"{path}/revenue/values",
        json={
            "values": [
                {"date": "2030-02-01", "value": 2000},
                {"date": "2030-01-01", "value": 1000},
                {"date": "2030-01-01", "value": 1250.5},
            ],
        },
    )

    assert replace_response.status_code == 200
    assert replace_response.json()["values"] == [
        {"date": "2030-01-01", "value": 1250.5},
        {"date": "2030-02-01", "value": 2000},
    ]

    omit_response = client.patch(
        f"{path}/revenue/values",
        json={"values": [{"date": "2030-02-01", "value": 2100}]},
    )

    assert omit_response.status_code == 200
    assert omit_response.json()["values"] == [
        {"date": "2030-02-01", "value": 2100},
    ]

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, "reality")
        revenue = session.scalar(
            select(Timeserie).where(
                Timeserie.scenario_id == scenario.scenario_id,
                Timeserie.timeserie_key == "revenue",
            ),
        )
        assert revenue is not None
        january = session.scalar(
            select(TimeserieValue).where(
                TimeserieValue.timeserie_id == revenue.timeserie_id,
                TimeserieValue.date == date(2030, 1, 1),
            ),
        )
        february = session.scalar(
            select(TimeserieValue).where(
                TimeserieValue.timeserie_id == revenue.timeserie_id,
                TimeserieValue.date == date(2030, 2, 1),
            ),
        )

        assert january is not None
        assert january.deleted_time is not None
        assert february is not None
        assert february.deleted_time is None
        assert february.value == {"value": 2100}


def test_timeserie_values_replace_string_and_boolean_values(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    path = f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"
    assert (
        client.post(
            path,
            json={
                "id": "status",
                "name": "Status",
                "timeUnit": "day",
                "valueUnit": "string",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            path,
            json={
                "id": "open",
                "name": "Open",
                "timeUnit": "year",
                "valueUnit": "boolean",
            },
        ).status_code
        == 201
    )

    string_response = client.patch(
        f"{path}/status/values",
        json={"values": [{"date": "2030-01-02", "value": "ready"}]},
    )
    boolean_response = client.patch(
        f"{path}/open/values",
        json={"values": [{"date": "2030-01-01", "value": False}]},
    )

    assert string_response.status_code == 200
    assert string_response.json()["values"] == [
        {"date": "2030-01-02", "value": "ready"},
    ]
    assert boolean_response.status_code == 200
    assert boolean_response.json()["values"] == [
        {"date": "2030-01-01", "value": False},
    ]


def test_timeserie_values_reject_invalid_value_types_and_start_dates(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    path = f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"
    assert (
        client.post(
            path,
            json={
                "id": "revenue",
                "name": "Revenue",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            path,
            json={
                "id": "capacity",
                "name": "Capacity",
                "timeUnit": "week",
                "valueUnit": "boolean",
            },
        ).status_code
        == 201
    )

    assert (
        client.patch(
            f"{path}/revenue/values",
            json={"values": [{"date": "2030-01-01", "value": "1000"}]},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{path}/revenue/values",
            json={"values": [{"date": "2030-01-01", "value": 10**400}]},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{path}/revenue/values",
            json={"values": [{"date": "2030-01-02", "value": 1000}]},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{path}/capacity/values",
            json={"values": [{"date": "2030-01-08", "value": True}]},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{path}/capacity/values",
            json={"values": [{"date": "2030-01-07", "value": 1}]},
        ).status_code
        == 422
    )


def test_timeserie_delete_soft_deletes_values_and_clears_graph_node_links(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    organisation_key = _create_organisation(client)
    path = f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"

    create_response = client.post(
        path,
        json={
            "id": "capacity",
            "name": "Capacity",
            "timeUnit": "week",
            "valueUnit": "number",
        },
    )
    assert create_response.status_code == 201

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, "reality")
        org_state = _get_org_state(session, scenario, "initial_state")
        timeserie = session.scalar(
            select(Timeserie).where(
                Timeserie.scenario_id == scenario.scenario_id,
                Timeserie.timeserie_key == "capacity",
            ),
        )
        node_type = session.scalar(
            select(NodeType)
            .where(NodeType.node_type_key == "nt_person")
            .order_by(NodeType.metamodel_id.desc()),
        )
        assert timeserie is not None
        assert node_type is not None
        node = GraphNode(
            scenario_id=scenario.scenario_id,
            node_key="node_capacity",
            name="Capacity node",
            node_type_id=node_type.node_type_id,
            create_date=org_state.target_date,
            attributes={},
            timeserie_id=timeserie.timeserie_id,
            timeserie_secondary_id=timeserie.timeserie_id,
        )
        value = TimeserieValue(
            timeserie_id=timeserie.timeserie_id,
            date=date(2026, 1, 1),
            value={"value": 10},
        )
        session.add_all([node, value])
        session.commit()

    delete_response = client.delete(f"{path}/capacity")

    assert delete_response.status_code == 204
    assert client.get(f"{path}/capacity").status_code == 404
    assert client.get(f"{path}/capacity/exists").json() == {
        "id": "capacity",
        "exists": False,
        "shortName": "",
        "shortNameEditable": True,
    }

    with session_factory() as session:
        organisation = _get_organisation(session, organisation_key)
        scenario = _get_scenario(session, organisation, "reality")
        timeserie = session.scalar(
            select(Timeserie).where(
                Timeserie.scenario_id == scenario.scenario_id,
                Timeserie.timeserie_key == "capacity",
            ),
        )
        assert timeserie is not None
        value = session.scalar(
            select(TimeserieValue).where(
                TimeserieValue.timeserie_id == timeserie.timeserie_id,
            ),
        )
        node = session.scalar(
            select(GraphNode).where(GraphNode.scenario_id == scenario.scenario_id),
        )

        assert timeserie.deleted_time is not None
        assert value is not None
        assert value.deleted_time is not None
        assert node is not None
        assert node.timeserie_id is None
        assert node.timeserie_secondary_id is None


def test_derived_metrics_materialize_recalculate_and_lock_short_names(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    path = f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries"
    for metric_id, short_name in (("revenue", "revenue"), ("cost", "cost")):
        response = client.post(
            path,
            json={
                "id": metric_id,
                "name": metric_id.title(),
                "shortName": short_name,
                "timeUnit": "month",
                "valueUnit": "number",
            },
        )
        assert response.status_code == 201
        values = client.patch(
            f"{path}/{metric_id}/values",
            json={
                "values": [
                    {
                        "date": "2030-01-01",
                        "value": 100 if metric_id == "revenue" else 40,
                    }
                ]
            },
        )
        assert values.status_code == 200

    derived_path = (
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/derived-metrics"
    )
    created = client.post(
        derived_path,
        json={"name": "Average", "unit": "EUR", "formula": "(revenue + cost) / 2"},
    )
    assert created.status_code == 201
    derived = created.json()
    assert derived["isDerived"] is True
    assert derived["derivedFormula"] == "(revenue + cost) / 2"
    assert derived["unit"] == "EUR"
    assert derived["values"] == [{"date": "2030-01-01", "value": 70.0}]

    locked = client.patch(f"{path}/revenue/short-name", json={"shortName": "sales"})
    assert locked.status_code == 409

    removed = client.patch(f"{path}/cost/values", json={"values": []})
    assert removed.status_code == 200
    assert removed.json()["shortNameEditable"] is False
    assert client.get(f"{path}/{derived['id']}").json()["values"] == []

    updated = client.patch(
        f"{derived_path}/{derived['id']}",
        json={"name": "Revenue only", "unit": "USD", "formula": "revenue"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Revenue only"
    assert updated.json()["unit"] == "USD"
    assert updated.json()["values"] == [{"date": "2030-01-01", "value": 100.0}]
    assert (
        client.patch(
            f"{path}/cost/short-name", json={"shortName": "expenses"}
        ).status_code
        == 200
    )


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
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states",
        json={"name": "First state", "targetDate": "2032-01-01"},
    )
    second_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states",
        json={"name": "Second state", "targetDate": "2032-02-01"},
    )
    deleted_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states",
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
                TEST_ACTOR_USER_ID,
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
        graph_nodes = session.scalars(
            select(GraphNode)
            .where(GraphNode.scenario_id == scenario.scenario_id)
            .order_by(GraphNode.node_key),
        ).all()
        graph_edges = session.scalars(
            select(GraphEdge)
            .where(GraphEdge.scenario_id == scenario.scenario_id)
            .order_by(GraphEdge.edge_key),
        ).all()

        assert scenario.initial_state_id is None
        assert cleaned_first_state.deleted_time is not None
        assert cleaned_second_state.deleted_time is not None
        assert previously_deleted_state.deleted_time is not None
        assert active_org_states == []
        assert [node.node_key for node in graph_nodes] == [
            "node_cleanup_deleted",
            "node_cleanup_first",
            "node_cleanup_second",
        ]
        assert all(node.deleted_time is not None for node in graph_nodes)
        assert [edge.edge_key for edge in graph_edges] == [
            "edge_node_cleanup_deleted",
            "edge_node_cleanup_first",
            "edge_node_cleanup_second",
        ]
        assert all(edge.deleted_time is not None for edge in graph_edges)


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
            TEST_ACTOR_USER_ID,
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
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states",
        json={"name": "State one", "targetDate": "2033-01-01"},
    )
    second_state_response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states",
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
        f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states",
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
        session.add_all([event, timeserie])
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
            scenario_id=scenario.scenario_id,
            node_key="node_1",
            name="Node",
            node_type_id=node_type.node_type_id,
            create_date=org_state.target_date,
            attributes={"name": "Node"},
        )
        session.add(graph_node)
        session.flush()
        graph_edge = GraphEdge(
            scenario_id=scenario.scenario_id,
            edge_key="edge_1",
            name="Edge",
            edge_type_id=edge_type.edge_type_id,
            source_graph_node_id=graph_node.graph_node_id,
            target_graph_node_id=graph_node.graph_node_id,
            create_date=org_state.target_date,
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
        graph_node = session.scalar(
            select(GraphNode).where(GraphNode.scenario_id == scenario.scenario_id),
        )
        graph_edge = session.scalar(
            select(GraphEdge).where(GraphEdge.scenario_id == scenario.scenario_id),
        )

        assert scenario.deleted_time is not None
        assert org_state.deleted_time is not None
        assert event is not None
        assert event.deleted_time is not None
        assert timeserie.deleted_time is not None
        assert timeserie_value is not None
        assert timeserie_value.deleted_time is not None
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


def _get_event_including_deleted(
    session: Session,
    scenario: Scenario,
    event_key: str,
) -> Event:
    event = session.scalar(
        select(Event).where(
            Event.scenario_id == scenario.scenario_id,
            Event.event_key == event_key,
        ),
    )
    assert event is not None
    return event


def _add_graph_snapshot(
    session: Session,
    org_state: OrgState,
    node_type_id: int,
    edge_type_id: int,
    *,
    graph_name: str,
    node_key: str,
    timeserie_id: int | None = None,
    timeserie_secondary_id: int | None = None,
) -> None:
    graph_node = GraphNode(
        scenario_id=org_state.scenario_id,
        node_key=node_key,
        name=graph_name,
        node_type_id=node_type_id,
        create_date=org_state.target_date,
        attributes={"name": node_key},
        timeserie_id=timeserie_id,
        timeserie_secondary_id=timeserie_secondary_id or timeserie_id,
    )
    session.add(graph_node)
    session.flush()
    session.add(
        GraphEdge(
            scenario_id=org_state.scenario_id,
            edge_key=f"edge_{node_key}",
            name=f"Edge {node_key}",
            edge_type_id=edge_type_id,
            source_graph_node_id=graph_node.graph_node_id,
            target_graph_node_id=graph_node.graph_node_id,
            create_date=org_state.target_date,
            attributes={"weight": 1},
        ),
    )
