import hashlib
import re
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from auth_helpers import (
    TEST_ACTOR_USER_ID,
    TEST_CSRF_TOKEN,
    TEST_ORIGIN,
    authenticate_test_client,
)
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.customers.models import Contact, Customer, CustomerAddress
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
    GraphEdge,
    GraphNode,
    Metamodel,
    NodeType,
    TypeAttribute,
)
from app.api.v1.organisations.models import Organisation
from app.api.v1.users.models import AuthSession, User
from app.core.config import Settings
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app

# (app configuration, method, sample path)
BusinessRoute = tuple[str, str, str]

# The sweep builds the app with default settings and with the MCP-gated
# routes (`/api/v1/ai/*`) registered.
APP_CONFIGURATIONS = {
    "default": Settings(),
    "mcp-enabled": Settings.model_validate({"MCP_ENABLED": True}),
}


def _registered_business_routes() -> tuple[BusinessRoute, ...]:
    routes: list[BusinessRoute] = []
    for configuration, settings in APP_CONFIGURATIONS.items():
        paths = cast(
            dict[str, dict[str, object]],
            create_app(settings=settings).openapi()["paths"],
        )
        for path, operations in paths.items():
            if not path.startswith("/api/v1/") or path.startswith("/api/v1/auth"):
                continue
            sample_path = re.sub(
                r"\{([^}]+)\}",
                lambda match: (
                    "999"
                    if match.group(1)
                    in {"user_id", "customer_id", "contact_id", "address_id"}
                    else "missing"
                ),
                path,
            )
            routes.extend(
                (configuration, method.upper(), sample_path)
                for method in operations
                if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
            )
    return tuple(routes)


BUSINESS_ROUTES = _registered_business_routes()

UNSAFE_BUSINESS_ROUTES = tuple(
    route for route in BUSINESS_ROUTES if route[1] in {"POST", "PUT", "PATCH", "DELETE"}
)
ADMIN_ROUTES = tuple(
    route
    for route in BUSINESS_ROUTES
    if route[2].startswith(("/api/v1/users", "/api/v1/ai/users/"))
)


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
    engine.dispose()


@contextmanager
def _client(
    session_factory: sessionmaker[Session],
    *,
    role: str | None = None,
    configuration: str = "default",
) -> Generator[TestClient, None, None]:
    app = create_app(settings=APP_CONFIGURATIONS[configuration])

    def override_get_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as client:
        if role is not None:
            authenticate_test_client(client, session_factory, role=role)
        yield client
    app.dependency_overrides.clear()


def test_sweep_covers_mcp_gated_routes_only_when_enabled() -> None:
    consent_routes = {
        (configuration, method)
        for configuration, method, path in BUSINESS_ROUTES
        if path.startswith("/api/v1/ai/oauth/consent")
    }

    assert consent_routes == {("mcp-enabled", "GET"), ("mcp-enabled", "POST")}


def test_sweep_covers_connections_routes_in_both_configurations() -> None:
    connection_routes = {
        route
        for route in BUSINESS_ROUTES
        if route[2].startswith(("/api/v1/ai/connections", "/api/v1/ai/users/"))
    }

    assert connection_routes == {
        (configuration, method, path)
        for configuration in APP_CONFIGURATIONS
        for method, path in (
            ("GET", "/api/v1/ai/connections"),
            ("DELETE", "/api/v1/ai/connections/missing"),
            ("POST", "/api/v1/ai/users/999/connections/revoke"),
        )
    }
    assert {
        (configuration, method)
        for configuration, method, path in ADMIN_ROUTES
        if path.startswith("/api/v1/ai/users/")
    } == {("default", "POST"), ("mcp-enabled", "POST")}


@pytest.mark.parametrize(("configuration", "method", "path"), BUSINESS_ROUTES)
def test_every_business_route_rejects_anonymous_requests(
    session_factory: sessionmaker[Session], configuration: str, method: str, path: str
) -> None:
    with _client(session_factory, configuration=configuration) as client:
        response = client.request(method, path, json={})

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "AUTHENTICATION_REQUIRED",
            "message": "Authentication required",
        }
    }


@pytest.mark.parametrize(("configuration", "method", "path"), UNSAFE_BUSINESS_ROUTES)
def test_every_unsafe_business_route_rejects_mismatched_origin(
    session_factory: sessionmaker[Session], configuration: str, method: str, path: str
) -> None:
    with _client(
        session_factory, role="admin", configuration=configuration
    ) as client:
        response = client.request(
            method,
            path,
            json={},
            headers={
                "Origin": "https://attacker.example",
                "X-CSRF-Token": TEST_CSRF_TOKEN,
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(
    "headers",
    [
        [],
        [("Origin", "null"), ("X-CSRF-Token", TEST_CSRF_TOKEN)],
        [("Origin", TEST_ORIGIN)],
        [("Origin", TEST_ORIGIN), ("X-CSRF-Token", "wrong")],
        [
            ("Origin", TEST_ORIGIN),
            ("Origin", TEST_ORIGIN),
            ("X-CSRF-Token", TEST_CSRF_TOKEN),
        ],
    ],
)
def test_business_unsafe_guard_rejects_missing_null_duplicate_or_invalid_data(
    session_factory: sessionmaker[Session], headers: list[tuple[str, str]]
) -> None:
    with _client(session_factory, role="consultant") as client:
        del client.headers["Origin"]
        del client.headers["X-CSRF-Token"]
        response = client.post(
            "/api/v1/customers",
            json={"name": "Rejected"},
            headers=headers,
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize(("configuration", "method", "path"), ADMIN_ROUTES)
def test_consultants_cannot_administer_users(
    session_factory: sessionmaker[Session], configuration: str, method: str, path: str
) -> None:
    with _client(
        session_factory, role="consultant", configuration=configuration
    ) as client:
        response = client.request(method, path, json={})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("role", ["admin", "consultant"])
def test_both_roles_can_access_every_organisation(
    session_factory: sessionmaker[Session], role: str
) -> None:
    with _client(session_factory, role=role) as client:
        first = client.post("/api/v1/organisations", json={"name": "First"})
        second = client.post("/api/v1/organisations", json={"name": "Second"})
        assert first.status_code == 201
        assert second.status_code == 201

        for organisation in (first.json(), second.json()):
            response = client.get(
                f"/api/v1/organisations/{organisation['id']}/scenarios"
            )
            assert response.status_code == 200
            assert response.json()[0]["id"] == "reality"


def test_admin_can_revoke_all_own_sessions(
    session_factory: sessionmaker[Session],
) -> None:
    now = datetime.now(UTC)
    with _client(session_factory, role="admin") as client:
        with session_factory() as session:
            session.add(
                AuthSession(
                    session_id_hash=hashlib.sha256(("x" * 43).encode()).digest(),
                    user_id=TEST_ACTOR_USER_ID,
                    csrf_token="second-csrf",
                    created_time=now,
                    last_activity_time=now,
                    absolute_expires_time=now + timedelta(hours=8),
                )
            )
            session.commit()

        response = client.post(f"/api/v1/users/{TEST_ACTOR_USER_ID}/sessions/revoke")
        assert response.status_code == 204
        assert client.get("/api/v1/users").status_code == 401

        with session_factory() as session:
            assert session.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_session_revocation_uses_active_user_not_found_behavior(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, role="admin") as client:
        assert client.post("/api/v1/users/999/sessions/revoke").status_code == 404
        target = client.post(
            "/api/v1/users",
            json={
                "name": "Deleted Target",
                "email": "deleted-target@example.test",
                "role": "consultant",
            },
        ).json()
        assert client.delete(f"/api/v1/users/{target['id']}").status_code == 204
        assert (
            client.post(f"/api/v1/users/{target['id']}/sessions/revoke").status_code
            == 404
        )


@pytest.mark.parametrize("inactive_state", ["deleted", "expired"])
def test_deleted_or_expired_session_users_immediately_lose_access(
    session_factory: sessionmaker[Session], inactive_state: str
) -> None:
    with _client(session_factory, role="consultant") as client:
        with session_factory() as session:
            if inactive_state == "deleted":
                user = session.get(User, TEST_ACTOR_USER_ID)
                assert user is not None
                user.deleted_time = datetime.now(UTC)
            else:
                auth_session = session.scalar(select(AuthSession))
                assert auth_session is not None
                auth_session.created_time = datetime.now(UTC) - timedelta(hours=1)
                auth_session.last_activity_time = datetime.now(UTC) - timedelta(
                    minutes=31
                )
            session.commit()

        response = client.get("/api/v1/customers")

    assert response.status_code == 401


def test_users_and_organisation_defaults_persist_audit_actors(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, role="admin") as client:
        created_user = client.post(
            "/api/v1/users",
            json={
                "name": "Audit Target",
                "email": "audit-target@example.test",
                "role": "consultant",
            },
        ).json()
        assert (
            client.patch(
                f"/api/v1/users/{created_user['id']}",
                json={"name": "Updated Target"},
            ).status_code
            == 200
        )
        assert client.delete(f"/api/v1/users/{created_user['id']}").status_code == 204

        created_org = client.post(
            "/api/v1/organisations", json={"name": "Audit Org"}
        ).json()
        assert (
            client.patch(
                f"/api/v1/organisations/{created_org['id']}",
                json={"name": "Updated Audit Org"},
            ).status_code
            == 200
        )

        with session_factory() as session:
            user = session.get(User, int(created_user["id"]))
            organisation = session.scalar(
                select(Organisation).where(
                    Organisation.organisation_key == created_org["id"]
                )
            )
            assert user is not None
            assert (user.created_by, user.modified_by, user.deleted_by) == (0, 0, 0)
            assert organisation is not None
            assert organisation.created_by == 0
            assert organisation.modified_by == 0

            scenario = session.scalar(
                select(Scenario).where(
                    Scenario.organisation_id == organisation.organisation_id
                )
            )
            metamodel = session.scalar(
                select(Metamodel).where(
                    Metamodel.organisation_id == organisation.organisation_id
                )
            )
            assert scenario is not None
            assert scenario.created_by == 0
            assert scenario.modified_by == 0
            assert metamodel is not None
            assert metamodel.created_by == 0
            org_state = session.scalar(
                select(OrgState).where(OrgState.scenario_id == scenario.scenario_id)
            )
            assert org_state is not None
            assert org_state.created_by == 0
            for model in (NodeType, EdgeType, TypeAttribute, AllowedConnection):
                rows = session.scalars(
                    select(model).where(model.metamodel_id == metamodel.metamodel_id)
                ).all()
                assert rows
                assert all(row.created_by == 0 for row in rows)

        assert (
            client.delete(f"/api/v1/organisations/{created_org['id']}").status_code
            == 204
        )
        with session_factory() as session:
            organisation = session.scalar(
                select(Organisation).where(
                    Organisation.organisation_key == created_org["id"]
                )
            )
            assert organisation is not None
            assert (organisation.modified_by, organisation.deleted_by) == (0, 0)


def test_customer_nested_mutations_persist_audit_actors(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, role="consultant") as client:
        customer = client.post(
            "/api/v1/customers", json={"name": "Audit Customer"}
        ).json()
        customer_path = f"/api/v1/customers/{customer['id']}"
        contact = client.post(
            f"{customer_path}/contacts", json={"name": "Audit Contact"}
        ).json()
        cascaded_contact = client.post(
            f"{customer_path}/contacts", json={"name": "Cascaded Contact"}
        ).json()
        address = client.post(
            f"{customer_path}/addresses",
            json={
                "label": "Audit Address",
                "addressLine1": "Street 1",
                "countryCode": "FI",
            },
        ).json()
        cascaded_address = client.post(
            f"{customer_path}/addresses",
            json={
                "label": "Cascaded Address",
                "addressLine1": "Street 3",
                "countryCode": "FI",
            },
        ).json()
        assert (
            client.put(
                customer_path,
                json={"name": "Updated Customer", "status": "archived"},
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"{customer_path}/contacts/{contact['id']}",
                json={"name": "Updated Contact"},
            ).status_code
            == 200
        )
        assert (
            client.put(
                f"{customer_path}/addresses/{address['id']}",
                json={
                    "label": "Updated Address",
                    "addressLine1": "Street 2",
                    "countryCode": "FI",
                },
            ).status_code
            == 200
        )
        assert (
            client.delete(f"{customer_path}/contacts/{contact['id']}").status_code
            == 204
        )
        assert (
            client.delete(f"{customer_path}/addresses/{address['id']}").status_code
            == 204
        )
        assert client.delete(customer_path).status_code == 204

        with session_factory() as session:
            customer_row = session.get(Customer, int(customer["id"]))
            contact_row = session.get(Contact, int(contact["id"]))
            address_row = session.get(CustomerAddress, int(address["id"]))
            cascaded_contact_row = session.get(Contact, int(cascaded_contact["id"]))
            cascaded_address_row = session.get(
                CustomerAddress, int(cascaded_address["id"])
            )
            assert customer_row is not None
            assert contact_row is not None
            assert address_row is not None
            assert cascaded_contact_row is not None
            assert cascaded_address_row is not None
            for row in (
                customer_row,
                contact_row,
                address_row,
                cascaded_contact_row,
                cascaded_address_row,
            ):
                assert row.created_by == 0
                assert row.modified_by == 0
                assert row.deleted_by == 0


def test_scenario_state_event_and_timeserie_mutations_persist_audit_actors(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, role="consultant") as client:
        organisation_key = client.post(
            "/api/v1/organisations", json={"name": "Planning Audit Org"}
        ).json()["id"]
        scenarios_path = f"/api/v1/organisations/{organisation_key}/scenarios"
        scenario = client.post(scenarios_path, json={"name": "Audit Scenario"}).json()
        scenario_path = f"{scenarios_path}/{scenario['id']}"
        assert (
            client.patch(scenario_path, json={"name": "Updated Scenario"}).status_code
            == 200
        )

        states_path = f"{scenario_path}/org-states"
        state = client.post(
            states_path,
            json={"name": "Audit State", "targetDate": "2030-01-01"},
        ).json()
        assert (
            client.patch(
                f"{states_path}/{state['id']}", json={"name": "Updated State"}
            ).status_code
            == 200
        )

        events_path = f"{scenario_path}/events"
        event = client.post(
            events_path,
            json={"name": "Audit Event", "targetDate": "2030-02-01"},
        ).json()
        event_path = f"{events_path}/{event['id']}"
        assert (
            client.patch(event_path, json={"name": "Updated Event"}).status_code == 200
        )
        assert client.delete(event_path).status_code == 204

        timeseries_path = f"{scenario_path}/timeseries"
        assert (
            client.post(
                timeseries_path,
                json={
                    "id": "audit-values",
                    "name": "Audit Values",
                    "timeUnit": "month",
                    "valueUnit": "number",
                },
            ).status_code
            == 201
        )
        values_path = f"{timeseries_path}/audit-values/values"
        assert (
            client.patch(
                values_path,
                json={
                    "values": [
                        {"date": "2030-01-01", "value": 1},
                        {"date": "2030-02-01", "value": 2},
                    ]
                },
            ).status_code
            == 200
        )
        assert (
            client.patch(
                values_path,
                json={"values": [{"date": "2030-02-01", "value": 3}]},
            ).status_code
            == 200
        )

        with session_factory() as session:
            scenario_row = session.scalar(
                select(Scenario).where(Scenario.scenario_key == scenario["id"])
            )
            assert scenario_row is not None
            state_row = session.scalar(
                select(OrgState).where(OrgState.org_state_key == state["id"])
            )
            event_row = session.scalar(
                select(Event).where(Event.event_key == event["id"])
            )
            timeserie = session.scalar(
                select(Timeserie).where(Timeserie.timeserie_key == "audit-values")
            )
            assert state_row is not None
            assert event_row is not None
            assert timeserie is not None
            assert (scenario_row.created_by, scenario_row.modified_by) == (0, 0)
            assert (state_row.created_by, state_row.modified_by) == (0, 0)
            assert (
                event_row.created_by,
                event_row.modified_by,
                event_row.deleted_by,
            ) == (
                0,
                0,
                0,
            )
            assert (timeserie.created_by, timeserie.modified_by) == (0, 0)
            values = session.scalars(
                select(TimeserieValue).where(
                    TimeserieValue.timeserie_id == timeserie.timeserie_id
                )
            ).all()
            assert all(value.created_by == 0 for value in values)
            assert all(value.modified_by == 0 for value in values)
            omitted = next(value for value in values if value.date.month == 1)
            assert omitted.deleted_by == 0

        assert client.delete(f"{timeseries_path}/audit-values").status_code == 204
        assert client.delete(f"{states_path}/{state['id']}").status_code == 204
        assert client.delete(scenario_path).status_code == 204

        clean_scenario = client.post(
            scenarios_path, json={"name": "Clean Audit Scenario"}
        ).json()
        clean_states_path = f"{scenarios_path}/{clean_scenario['id']}/org-states"
        clean_state = client.post(
            clean_states_path,
            json={"name": "Cleaned State", "targetDate": "2040-01-01"},
        ).json()
        assert client.post(f"{clean_states_path}/clean").status_code == 200
        with session_factory() as session:
            scenario_row = session.scalar(
                select(Scenario).where(Scenario.scenario_key == scenario["id"])
            )
            state_row = session.scalar(
                select(OrgState).where(OrgState.org_state_key == state["id"])
            )
            timeserie = session.scalar(
                select(Timeserie).where(Timeserie.timeserie_key == "audit-values")
            )
            assert scenario_row is not None
            assert state_row is not None
            assert timeserie is not None
            clean_state_row = session.scalar(
                select(OrgState).where(OrgState.org_state_key == clean_state["id"])
            )
            assert clean_state_row is not None
            assert (scenario_row.modified_by, scenario_row.deleted_by) == (0, 0)
            assert (state_row.modified_by, state_row.deleted_by) == (0, 0)
            assert (timeserie.modified_by, timeserie.deleted_by) == (0, 0)
            assert (clean_state_row.modified_by, clean_state_row.deleted_by) == (0, 0)


def test_structure_mutations_and_scenario_copy_persist_audit_actors(
    session_factory: sessionmaker[Session],
) -> None:
    with _client(session_factory, role="consultant") as client:
        organisation_key = client.post(
            "/api/v1/organisations", json={"name": "Structure Audit Org"}
        ).json()["id"]
        graph_path = (
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            "org-states/initial_state/graph"
        )
        for node_id in ("source", "target"):
            assert (
                client.post(
                    f"{graph_path}/nodes",
                    json={
                        "id": node_id,
                        "name": node_id.title(),
                        "nodeTypeId": "nt_person",
                    },
                ).status_code
                == 201
            )
        edge = client.post(
            f"{graph_path}/edges",
            json={
                "id": "audit-edge",
                "name": "Audit Edge",
                "edgeTypeId": "et_reports_to",
                "sourceNodeId": "source",
                "targetNodeId": "target",
            },
        )
        assert edge.status_code == 201
        individual_edge = client.post(
            f"{graph_path}/edges",
            json={
                "id": "individual-edge",
                "name": "Individual Edge",
                "edgeTypeId": "et_reports_to",
                "sourceNodeId": "target",
                "targetNodeId": "source",
            },
        )
        assert individual_edge.status_code == 201
        assert (
            client.patch(
                f"{graph_path}/nodes/source", json={"name": "Updated Source"}
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"{graph_path}/edges/audit-edge", json={"name": "Updated Edge"}
            ).status_code
            == 200
        )
        assert (
            client.patch(
                f"{graph_path}/positions",
                json={"positions": [{"nodeId": "target", "x": 10, "y": 20}]},
            ).status_code
            == 200
        )

        copied = client.post(
            f"/api/v1/organisations/{organisation_key}/scenarios/copy",
            json={
                "sourceScenarioId": "reality",
                "sourceOrgStateId": "initial_state",
                "name": "Copied Audit Scenario",
            },
        )
        assert copied.status_code == 201

        assert client.delete(f"{graph_path}/edges/individual-edge").status_code == 204
        assert client.delete(f"{graph_path}/nodes/source").status_code == 204
        with session_factory() as session:
            original = session.scalar(
                select(Scenario).where(Scenario.scenario_key == "reality")
            )
            copied_scenario = session.scalar(
                select(Scenario).where(Scenario.scenario_key == copied.json()["id"])
            )
            assert original is not None
            assert copied_scenario is not None
            original_nodes = session.scalars(
                select(GraphNode).where(GraphNode.scenario_id == original.scenario_id)
            ).all()
            original_edges = session.scalars(
                select(GraphEdge).where(GraphEdge.scenario_id == original.scenario_id)
            ).all()
            copied_nodes = session.scalars(
                select(GraphNode).where(
                    GraphNode.scenario_id == copied_scenario.scenario_id
                )
            ).all()
            copied_edges = session.scalars(
                select(GraphEdge).where(
                    GraphEdge.scenario_id == copied_scenario.scenario_id
                )
            ).all()
            all_nodes = [*original_nodes, *copied_nodes]
            all_edges = [*original_edges, *copied_edges]
            assert all(node.created_by == 0 for node in all_nodes)
            assert all(edge.created_by == 0 for edge in all_edges)
            source = next(node for node in original_nodes if node.node_key == "source")
            target = next(node for node in original_nodes if node.node_key == "target")
            assert (source.modified_by, source.deleted_by) == (0, 0)
            assert target.modified_by == 0
            assert all(
                (original_edge.modified_by, original_edge.deleted_by) == (0, 0)
                for original_edge in original_edges
            )
            assert copied_scenario.created_by == 0
            copied_state = session.scalar(
                select(OrgState).where(
                    OrgState.scenario_id == copied_scenario.scenario_id
                )
            )
            assert copied_state is not None
            assert copied_state.created_by == 0


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
        session.add(
            TypeAttribute(
                metamodel_id=metamodel.metamodel_id,
                owner_kind="node_type",
                owner_node_type_id=node_type.node_type_id,
                attribute_key="name",
                name="Name",
                display_name="Name",
                data_type="string",
                mandatory=True,
            )
        )
        session.add(
            AllowedConnection(
                metamodel_id=metamodel.metamodel_id,
                edge_type_id=edge_type.edge_type_id,
                source_node_type_id=node_type.node_type_id,
                target_node_type_id=node_type.node_type_id,
            )
        )
        session.commit()
