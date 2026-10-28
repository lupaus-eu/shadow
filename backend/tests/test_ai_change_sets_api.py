# pyright: reportPrivateUsage=false

import os

os.environ["APP_ENV"] = "test"
from collections.abc import Generator, Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from typing import Any

import psycopg
import pytest
from auth_helpers import authenticate_test_client
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import StaticPool, create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.ai_change_sets.engine as engine
import app.api.v1.ai_change_sets.service as change_sets_service
from app.api.v1.ai_change_sets.models import AiChangeSet, AiChangeSetOperation
from app.api.v1.ai_change_sets.schemas import OPERATION_ADAPTER
from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import Scenario, Timeserie
from app.api.v1.org_states.schemas import (
    ScenarioCreateRequest,
    TimeserieCreateRequest,
    TimeserieValueRequest,
    TimeserieValuesPatchRequest,
)
from app.api.v1.org_twin_structure import org_twin_structure_service
from app.api.v1.org_twin_structure.models import Metamodel, NodeType
from app.api.v1.org_twin_structure.schemas import GraphNodeCreateRequest
from app.api.v1.organisations import service as organisations_service
from app.api.v1.organisations.schemas import OrganisationCreateRequest
from app.api.v1.users.models import User
from app.core.config import Settings
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app

CREATOR_USER_ID = 7
REVIEWER_USER_ID = 8
STALE_FINGERPRINT = "0" * 64
MONTHLY_SPEC: dict[str, Any] = {
    "startDate": "2026-01-01",
    "periods": 12,
    "timeUnit": "month",
    "baseLevel": 10,
    "seed": 7,
}


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    database = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(database)
    factory = sessionmaker(bind=database, autocommit=False, autoflush=False)
    with factory() as session:
        session.add(
            User(
                user_id=CREATOR_USER_ID,
                name="AI Creator",
                email="creator@example.test",
                role="consultant",
            )
        )
        metamodel = Metamodel(version=1)
        session.add(metamodel)
        session.flush()
        session.add(
            NodeType(
                metamodel_id=metamodel.metamodel_id,
                node_type_key="nt_person",
                name="Person",
                display_name="Person",
                ui_color="#FECDC2",
                ui_shape="rectangle",
            )
        )
        session.commit()
    yield factory
    database.dispose()


@pytest.fixture()
def organisation_key(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        return organisations_service.create_organisation(
            session, OrganisationCreateRequest(name="Acme Corp"), CREATOR_USER_ID
        ).id


@contextmanager
def _client(
    session_factory: sessionmaker[Session],
    *,
    user_id: int = REVIEWER_USER_ID,
    role: str = "admin",
) -> Generator[TestClient, None, None]:
    # Default settings: MCP is disabled and the review API stays registered.
    app = create_app(settings=Settings())

    def override_get_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as client:
        authenticate_test_client(
            client,
            session_factory,
            user_id=user_id,
            role=role,
            create_user=user_id != CREATOR_USER_ID,
        )
        yield client
    app.dependency_overrides.clear()


def _timeserie(key: str, scenario_key: str = "reality") -> dict[str, Any]:
    return {
        "type": "create_timeserie",
        "scenario_key": scenario_key,
        "payload": {
            "id": key,
            "name": key.title(),
            "timeUnit": "month",
            "valueUnit": "number",
        },
    }


def _set_values(key: str, *values: tuple[str, float]) -> dict[str, Any]:
    return {
        "type": "set_timeserie_values",
        "scenario_key": "reality",
        "timeserie_key": key,
        "payload": {"values": [{"date": day, "value": value} for day, value in values]},
    }


def _staged(
    factory: sessionmaker[Session],
    organisation_key: str,
    raw_operations: Sequence[dict[str, Any]],
    *,
    submit: bool = True,
) -> str:
    with factory() as session:
        change_set = engine.create_change_set(
            session,
            organisation_key,
            title="AI plan",
            rationale="Generated with the user.",
            created_by=CREATOR_USER_ID,
            grant_id=None,
            client_id="client-1",
            client_name="Claude <Desktop>",
        )
        engine.add_operations(
            session,
            change_set,
            [OPERATION_ADAPTER.validate_python(item) for item in raw_operations],
            CREATOR_USER_ID,
        )
        session.commit()
        change_set_key = change_set.change_set_key
    if submit:
        with factory() as session:
            change_set = _load(session, change_set_key)
            assert engine.submit_change_set(
                session, factory, change_set, CREATOR_USER_ID
            ).ok
            session.commit()
    return change_set_key


def _load(session: Session, change_set_key: str) -> AiChangeSet:
    change_set = session.scalar(
        select(AiChangeSet).where(AiChangeSet.change_set_key == change_set_key)
    )
    assert change_set is not None
    return change_set


def _stored(factory: sessionmaker[Session], change_set_key: str) -> AiChangeSet:
    with factory() as session:
        change_set = _load(session, change_set_key)
        session.expunge(change_set)
        return change_set


def _timeserie_count(factory: sessionmaker[Session], key: str) -> int:
    with factory() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(Timeserie)
                .where(Timeserie.timeserie_key == key)
            )
            or 0
        )


def _create_revenue(
    factory: sessionmaker[Session],
    organisation_key: str,
    values: Sequence[tuple[date, float]] = (),
) -> None:
    with factory() as session:
        org_states_service.create_timeserie(
            session,
            organisation_key,
            "reality",
            TimeserieCreateRequest(
                id="revenue", name="Revenue", timeUnit="month", valueUnit="number"
            ),
            CREATOR_USER_ID,
        )
        if values:
            org_states_service.replace_timeserie_values(
                session,
                organisation_key,
                "reality",
                "revenue",
                TimeserieValuesPatchRequest(
                    values=[
                        TimeserieValueRequest(date=day, value=value)
                        for day, value in values
                    ]
                ),
                CREATOR_USER_ID,
            )


def _url(organisation_key: str, change_set_key: str = "", action: str = "") -> str:
    url = f"/api/v1/organisations/{organisation_key}/ai/change-sets"
    if change_set_key:
        url += f"/{change_set_key}"
    if action:
        url += f"/{action}"
    return url


def _fingerprint(client: TestClient, organisation_key: str, key: str) -> str:
    response = client.get(_url(organisation_key, key))
    assert response.status_code == 200
    return response.json()["reviewFingerprint"]


def _error_code(response: Any) -> str:
    return response.json()["error"]["code"]


def _query_cancelled() -> OperationalError:
    return OperationalError(
        "SELECT 1",
        {},
        psycopg.errors.QueryCanceled("canceling statement due to statement timeout"),
    )


def _lock_not_available() -> OperationalError:
    return OperationalError(
        "SELECT 1",
        {},
        psycopg.errors.LockNotAvailable("canceling statement due to lock timeout"),
    )


def test_list_filters_by_status_and_derived_scenario(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    with session_factory() as session:
        plan = org_states_service.create_scenario(
            session,
            organisation_key,
            ScenarioCreateRequest(name="Plan"),
            CREATOR_USER_ID,
        ).id
    reality_draft = _staged(
        session_factory, organisation_key, [_timeserie("a")], submit=False
    )
    reality = _staged(session_factory, organisation_key, [_timeserie("b")])
    in_plan = _staged(session_factory, organisation_key, [_timeserie("c", plan)])
    unscoped = _staged(
        session_factory,
        organisation_key,
        [{"type": "create_scenario", "payload": {"name": "AI plan"}}],
    )

    with _client(session_factory) as client:

        def keys(**params: str) -> list[str]:
            response = client.get(_url(organisation_key), params=params)
            assert response.status_code == 200, response.json()
            return [item["id"] for item in response.json()]

        assert keys() == [unscoped, in_plan, reality, reality_draft]
        assert keys(status="draft") == [reality_draft]
        assert keys(status="submitted") == [unscoped, in_plan, reality]
        assert keys(scenarioKey="reality") == [reality, reality_draft]
        assert keys(scenarioKey=plan) == [in_plan]
        assert keys(scenarioKey=plan, includeUnscoped="true") == [unscoped, in_plan]
        assert keys(scenarioKey="reality", status="submitted") == [reality]
        assert keys(limit="1") == [unscoped]

        item = client.get(_url(organisation_key), params={"limit": "1"}).json()[0]
        assert set(item) == {
            "id",
            "scenarioKey",
            "title",
            "rationale",
            "status",
            "operationCount",
            "clientId",
            "clientName",
            "createdBy",
            "createdByName",
            "createdTime",
            "modifiedTime",
            "reviewedBy",
            "reviewedByName",
            "reviewedTime",
            "reviewNote",
        }
        assert item["scenarioKey"] is None
        assert (item["clientId"], item["clientName"]) == (
            "client-1",
            "Claude <Desktop>",
        )
        assert (item["createdBy"], item["createdByName"]) == (
            CREATOR_USER_ID,
            "AI Creator",
        )

        missing = client.get(_url(organisation_key), params={"scenarioKey": "nope"})
        assert missing.status_code == 404
        invalid = client.get(_url(organisation_key), params={"status": "unknown"})
        assert invalid.status_code == 422
        assert client.get(_url("missing")).status_code == 404


def test_detail_shows_operations_frozen_values_and_validation(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key = _staged(
        session_factory,
        organisation_key,
        [
            {**_timeserie("headcount"), "scenario_key": "reality"},
            {
                "type": "generate_timeserie_values",
                "scenario_key": "reality",
                "timeserie_key": "headcount",
                "spec": MONTHLY_SPEC,
            },
        ],
    )

    with _client(session_factory, role="consultant") as client:
        detail = client.get(_url(organisation_key, change_set_key)).json()
        monkeypatch.setattr(change_sets_service, "INLINE_FROZEN_VALUES_LIMIT", 11)
        summarised = client.get(_url(organisation_key, change_set_key)).json()

    assert detail["id"] == change_set_key
    assert detail["status"] == "submitted"
    assert detail["scenarioKey"] == "reality"
    assert (detail["clientId"], detail["clientName"]) == (
        "client-1",
        "Claude <Desktop>",
    )
    assert detail["createdByName"] == "AI Creator"
    assert detail["validationResult"]["ok"] is True
    assert [item["status"] for item in detail["validationResult"]["operations"]] == [
        "ok",
        "ok",
    ]
    assert detail["appliedResult"] is None
    assert len(detail["reviewFingerprint"]) == 64

    create, generate = detail["operations"]
    assert create["operation"] == {
        "type": "create_timeserie",
        "scenario_key": "reality",
        "payload": {
            "id": "headcount",
            "name": "Headcount",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    }
    assert create["frozenValues"] is None
    assert (create["replacesExisting"], create["replaces"]) == (False, None)
    frozen = generate["frozenValues"]
    assert (frozen["valueCount"], frozen["firstDate"], frozen["lastDate"]) == (
        12,
        "2026-01-01",
        "2026-12-01",
    )
    assert frozen["generatorVersion"] >= 1
    assert len(frozen["values"]) == 12
    assert set(frozen["values"][0]) == {"date", "value"}

    large = summarised["operations"][1]["frozenValues"]
    assert large["values"] is None
    assert large["valueCount"] == 12


def test_detail_flags_replacements_against_current_data(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    _create_revenue(session_factory, organisation_key)
    with session_factory() as session:
        org_twin_structure_service.create_graph_node(
            session,
            organisation_key,
            "reality",
            "initial_state",
            GraphNodeCreateRequest(id="hq", name="HQ", nodeTypeId="nt_person"),
            CREATOR_USER_ID,
        )
    change_set_key = _staged(
        session_factory,
        organisation_key,
        [
            _set_values("revenue", ("2026-01-01", 1.0)),
            {
                "type": "patch_node",
                "scenario_key": "reality",
                "org_state_key": "initial_state",
                "node_key": "hq",
                "payload": {"name": "Head office", "nodeTypeId": "nt_person"},
            },
        ],
    )

    with _client(session_factory) as client:
        before = client.get(_url(organisation_key, change_set_key)).json()
        # Values added after submit make the operation replace existing data.
        _create_revenue_values(session_factory, organisation_key)
        after = client.get(_url(organisation_key, change_set_key)).json()
        with session_factory() as session:
            org_states_service.soft_delete_timeserie(
                session, organisation_key, "reality", "revenue", CREATOR_USER_ID
            )
        deleted = client.get(_url(organisation_key, change_set_key)).json()

    values_before, node = before["operations"]
    assert (values_before["replacesExisting"], values_before["replaces"]) == (
        False,
        None,
    )
    assert node["replacesExisting"] is True
    assert node["replaces"]["kind"] == "node"
    assert node["replaces"]["nodeKey"] == "hq"
    assert node["replaces"]["fields"] == {"name": "HQ", "nodeTypeId": "nt_person"}
    assert len(node["replaces"]["checksum"]) == 64

    values_after = after["operations"][0]
    assert values_after["replacesExisting"] is True
    assert values_after["replaces"] == {
        "kind": "timeserie",
        "scenarioKey": "reality",
        "timeserieKey": "revenue",
        "missing": False,
        "message": None,
        "valueCount": 2,
        "firstDate": "2026-01-01",
        "lastDate": "2026-02-01",
        "checksum": values_after["replaces"]["checksum"],
    }
    assert after["reviewFingerprint"] != before["reviewFingerprint"]

    missing = deleted["operations"][0]["replaces"]
    assert (missing["missing"], missing["message"]) == (True, "Timeserie not found.")
    assert deleted["reviewFingerprint"] != after["reviewFingerprint"]


def _create_revenue_values(
    factory: sessionmaker[Session], organisation_key: str
) -> None:
    with factory() as session:
        org_states_service.replace_timeserie_values(
            session,
            organisation_key,
            "reality",
            "revenue",
            TimeserieValuesPatchRequest(
                values=[
                    TimeserieValueRequest(date=date(2026, 1, 1), value=5),
                    TimeserieValueRequest(date=date(2026, 2, 1), value=6),
                ]
            ),
            CREATOR_USER_ID,
        )


def test_detail_is_scoped_to_the_organisation(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _staged(session_factory, organisation_key, [_timeserie("a")])
    with session_factory() as session:
        other = organisations_service.create_organisation(
            session, OrganisationCreateRequest(name="Other"), CREATOR_USER_ID
        ).id

    with _client(session_factory) as client:
        for response in (
            client.get(_url(other, change_set_key)),
            client.get(_url(organisation_key, "change_set_unknown")),
            client.post(
                _url(other, change_set_key, "apply"),
                json={"reviewFingerprint": STALE_FINGERPRINT},
            ),
            client.post(_url(other, change_set_key, "reject"), json={}),
        ):
            assert response.status_code == 404
            assert response.json() == {"detail": "Change set not found."}

    assert _stored(session_factory, change_set_key).status == "submitted"


@pytest.mark.parametrize(
    ("module", "target", "raised"),
    [
        # The flag recomputation.
        (engine, "compute_replacements", _query_cancelled),
        (engine, "compute_replacements", _lock_not_available),
        # The change-set lookup by key.
        (change_sets_service, "get_change_set", _query_cancelled),
    ],
    ids=["recomputation-timeout", "recomputation-lock", "lookup-timeout"],
)
def test_a_database_error_in_the_detail_is_a_retryable_503(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    target: str,
    raised: Any,
) -> None:
    change_set_key = _staged(session_factory, organisation_key, [_timeserie("a")])

    def fail(*_args: object, **_kwargs: object) -> object:
        raise raised()

    monkeypatch.setattr(module, target, fail)
    with _client(session_factory) as client:
        response = client.get(_url(organisation_key, change_set_key))

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "review_unavailable",
            "message": "The change set review could not be loaded right now. "
            "Try again shortly.",
        }
    }


def _validated_draft(factory: sessionmaker[Session], organisation_key: str) -> str:
    change_set_key = _staged(factory, organisation_key, [_timeserie("a")], submit=False)
    with factory() as session:
        assert engine.validate_change_set(
            session, factory, _load(session, change_set_key), CREATOR_USER_ID
        ).ok
        session.commit()
    return change_set_key


def _add_operation_as_mcp(factory: sessionmaker[Session], change_set_key: str) -> None:
    """An MCP edit of the draft that commits and clears its validation result."""
    with factory() as session:
        engine.add_operations(
            session,
            _load(session, change_set_key),
            [OPERATION_ADAPTER.validate_python(_timeserie("b"))],
            CREATOR_USER_ID,
        )
        session.commit()


def test_detail_reflects_an_edit_committed_after_its_lookup(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key = _validated_draft(session_factory, organisation_key)
    get_change_set = change_sets_service.get_change_set

    def edited_after_lookup(*args: Any, **kwargs: Any) -> Any:
        change_set = get_change_set(*args, **kwargs)
        _add_operation_as_mcp(session_factory, change_set_key)
        return change_set

    monkeypatch.setattr(change_sets_service, "get_change_set", edited_after_lookup)
    with _client(session_factory) as client:
        response = client.get(_url(organisation_key, change_set_key))

    assert response.status_code == 200, response.json()
    detail = response.json()
    # The detail statement refreshes the looked-up change set, so its stored
    # validation result is the one the edit cleared, like the rest.
    assert [item["position"] for item in detail["operations"]] == [0, 1]
    assert detail["operationCount"] == 2
    assert detail["validationResult"] is None


def test_detail_stays_consistent_while_a_draft_is_edited(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key = _validated_draft(session_factory, organisation_key)
    compute_replacements = engine.compute_replacements

    def edited_meanwhile(*args: Any, **kwargs: Any) -> Any:
        report = compute_replacements(*args, **kwargs)
        # The edit commits after the flags were computed.
        _add_operation_as_mcp(session_factory, change_set_key)
        return report

    monkeypatch.setattr(engine, "compute_replacements", edited_meanwhile)
    with _client(session_factory) as client:
        during = client.get(_url(organisation_key, change_set_key))
        monkeypatch.undo()
        after = client.get(_url(organisation_key, change_set_key))

    assert during.status_code == 200, during.json()
    detail = during.json()
    # Everything describes the one operation read before the edit committed.
    assert [item["position"] for item in detail["operations"]] == [0]
    assert detail["operationCount"] == 1
    assert len(detail["validationResult"]["operations"]) == 1
    # The edit cleared the stored validation result.
    detail = after.json()
    assert [item["position"] for item in detail["operations"]] == [0, 1]
    assert detail["operationCount"] == 2
    assert detail["validationResult"] is None


@pytest.mark.parametrize(
    ("user_id", "role"),
    [
        (REVIEWER_USER_ID, "admin"),
        (REVIEWER_USER_ID, "consultant"),
        (CREATOR_USER_ID, "consultant"),
    ],
)
def test_both_roles_and_the_creator_can_apply(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    user_id: int,
    role: str,
) -> None:
    change_set_key = _staged(
        session_factory,
        organisation_key,
        [
            {"type": "create_scenario", "ref": "$plan", "payload": {"name": "AI plan"}},
            _timeserie("headcount", "$plan"),
        ],
    )

    with _client(session_factory, user_id=user_id, role=role) as client:
        fingerprint = _fingerprint(client, organisation_key, change_set_key)
        response = client.post(
            _url(organisation_key, change_set_key, "apply"),
            json={"reviewFingerprint": fingerprint},
        )

    assert response.status_code == 200, response.json()
    body = response.json()
    plan_key = body["refs"]["$plan"]
    assert [
        (item["opType"], item["status"], item["scenarioKey"], item["key"])
        for item in body["operations"]
    ] == [
        ("create_scenario", "ok", plan_key, plan_key),
        ("create_timeserie", "ok", plan_key, "headcount"),
    ]
    change_set = body["changeSet"]
    assert (change_set["status"], change_set["reviewedBy"]) == ("applied", user_id)
    assert change_set["reviewedByName"] is not None
    assert change_set["reviewedTime"] is not None

    stored = _stored(session_factory, change_set_key)
    assert (stored.status, stored.reviewed_by, stored.modified_by) == (
        "applied",
        user_id,
        user_id,
    )
    with session_factory() as session:
        scenario = session.scalar(
            select(Scenario).where(Scenario.scenario_key == plan_key)
        )
        assert scenario is not None and scenario.created_by == user_id


def test_apply_requires_a_submitted_change_set(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    draft = _staged(session_factory, organisation_key, [_timeserie("a")], submit=False)
    submitted = _staged(session_factory, organisation_key, [_timeserie("b")])

    with _client(session_factory) as client:
        response = client.post(
            _url(organisation_key, draft, "apply"),
            json={"reviewFingerprint": STALE_FINGERPRINT},
        )
        assert response.status_code == 409
        assert _error_code(response) == "not_submitted"
        assert response.json()["error"]["message"].endswith("this one is draft.")

        fingerprint = _fingerprint(client, organisation_key, submitted)
        apply_url = _url(organisation_key, submitted, "apply")
        assert (
            client.post(apply_url, json={"reviewFingerprint": fingerprint}).status_code
            == 200
        )
        again = client.post(apply_url, json={"reviewFingerprint": fingerprint})

    assert again.status_code == 409
    assert _error_code(again) == "not_submitted"
    assert _stored(session_factory, draft).status == "draft"
    assert _stored(session_factory, submitted).status == "applied"
    assert _timeserie_count(session_factory, "a") == 0
    assert _timeserie_count(session_factory, "b") == 1


@pytest.mark.parametrize(
    "body",
    [{}, {"reviewFingerprint": ""}, {"reviewFingerprint": "abc"}, {"other": "x"}],
)
def test_apply_without_a_valid_fingerprint_is_rejected(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    body: dict[str, str],
) -> None:
    change_set_key = _staged(session_factory, organisation_key, [_timeserie("a")])

    with _client(session_factory) as client:
        response = client.post(
            _url(organisation_key, change_set_key, "apply"), json=body
        )

    assert response.status_code == 422
    assert _stored(session_factory, change_set_key).status == "submitted"
    assert _timeserie_count(session_factory, "a") == 0


def test_apply_with_a_stale_fingerprint_changes_nothing(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    _create_revenue(session_factory, organisation_key, [(date(2026, 1, 1), 5.0)])
    change_set_key = _staged(
        session_factory,
        organisation_key,
        [_set_values("revenue", ("2026-01-01", 1.0)), _timeserie("a")],
    )

    with _client(session_factory) as client:
        fingerprint = _fingerprint(client, organisation_key, change_set_key)
        _create_revenue_values(session_factory, organisation_key)
        apply_url = _url(organisation_key, change_set_key, "apply")
        stale = client.post(apply_url, json={"reviewFingerprint": fingerprint})
        unknown = client.post(apply_url, json={"reviewFingerprint": STALE_FINGERPRINT})

        for response in (stale, unknown):
            assert response.status_code == 409
            assert _error_code(response) == "review_stale"
        stored = _stored(session_factory, change_set_key)
        assert (stored.status, stored.applied_result, stored.reviewed_by) == (
            "submitted",
            None,
            None,
        )
        assert _timeserie_count(session_factory, "a") == 0

        fresh = _fingerprint(client, organisation_key, change_set_key)
        applied = client.post(apply_url, json={"reviewFingerprint": fresh})

    assert applied.status_code == 200
    with session_factory() as session:
        revenue = org_states_service.get_timeserie(
            session, organisation_key, "reality", "revenue"
        )
    assert [(value.date, value.value) for value in revenue.values] == [
        (date(2026, 1, 1), 1.0)
    ]


@pytest.mark.parametrize(
    ("target", "raised", "status_code", "code"),
    [
        # The lock step: another transaction holds the change set.
        ("get_active_organisation", _lock_not_available, 409, "apply_in_progress"),
        ("get_active_organisation", _query_cancelled, 503, "apply_unavailable"),
        # The fingerprint step: the recomputation hit the statement timeout.
        ("compute_replacements", _query_cancelled, 503, "apply_unavailable"),
    ],
)
def test_retryable_apply_errors_keep_the_change_set_submitted(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    raised: Any,
    status_code: int,
    code: str,
) -> None:
    change_set_key = _staged(session_factory, organisation_key, [_timeserie("a")])

    with _client(session_factory) as client:
        fingerprint = _fingerprint(client, organisation_key, change_set_key)

        def fail(*_args: object, **_kwargs: object) -> object:
            raise raised()

        monkeypatch.setattr(engine, target, fail)
        response = client.post(
            _url(organisation_key, change_set_key, "apply"),
            json={"reviewFingerprint": fingerprint},
        )

    assert response.status_code == status_code
    assert _error_code(response) == code
    if code == "apply_unavailable":
        assert "could not be applied" in response.json()["error"]["message"]
    stored = _stored(session_factory, change_set_key)
    assert (stored.status, stored.applied_result) == ("submitted", None)
    assert _timeserie_count(session_factory, "a") == 0


def test_an_operation_failure_marks_the_change_set_failed(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _staged(session_factory, organisation_key, [_timeserie("revenue")])
    # The same key is taken after submit, so re-validation fails.
    _create_revenue(session_factory, organisation_key)

    with _client(session_factory) as client:
        response = client.post(
            _url(organisation_key, change_set_key, "apply"),
            json={
                "reviewFingerprint": _fingerprint(
                    client, organisation_key, change_set_key
                )
            },
        )
        detail = client.get(_url(organisation_key, change_set_key)).json()

    assert response.status_code == 409
    assert _error_code(response) == "apply_failed"
    assert detail["status"] == "failed"
    assert detail["reviewedBy"] == REVIEWER_USER_ID
    assert detail["appliedResult"]["status"] == "failed"
    assert detail["appliedResult"]["step"] == "execute"
    assert detail["operations"][0]["error"]["code"] == "domain_error"
    assert _timeserie_count(session_factory, "revenue") == 1


@pytest.mark.parametrize(
    ("user_id", "role"),
    [
        (REVIEWER_USER_ID, "admin"),
        (REVIEWER_USER_ID, "consultant"),
        (CREATOR_USER_ID, "consultant"),
    ],
)
def test_reject_records_the_reviewer_and_note(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    user_id: int,
    role: str,
) -> None:
    change_set_key = _staged(session_factory, organisation_key, [_timeserie("a")])

    with _client(session_factory, user_id=user_id, role=role) as client:
        reject_url = _url(organisation_key, change_set_key, "reject")
        response = client.post(reject_url, json={"note": "  Wrong scenario.  "})
        again = client.post(reject_url)
        fingerprint = _fingerprint(client, organisation_key, change_set_key)
        apply = client.post(
            _url(organisation_key, change_set_key, "apply"),
            json={"reviewFingerprint": fingerprint},
        )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert (body["status"], body["reviewedBy"], body["reviewNote"]) == (
        "rejected",
        user_id,
        "Wrong scenario.",
    )
    assert body["reviewedTime"] is not None
    stored = _stored(session_factory, change_set_key)
    assert (
        stored.status,
        stored.reviewed_by,
        stored.modified_by,
        stored.review_note,
    ) == (
        "rejected",
        user_id,
        user_id,
        "Wrong scenario.",
    )
    assert stored.applied_result is None
    for terminal in (again, apply):
        assert terminal.status_code == 409
        assert _error_code(terminal) == "not_submitted"
    assert _timeserie_count(session_factory, "a") == 0


@pytest.mark.parametrize(
    ("body", "status_code", "note"),
    [
        (None, 200, None),
        ({}, 200, None),
        ({"note": "   "}, 200, None),
        ({"note": "x" * 2_000}, 200, "x" * 2_000),
        ({"note": "x" * 2_001}, 422, None),
        ({"note": "nul\x00"}, 422, None),
        ({"note": 5}, 422, None),
    ],
    ids=["no-body", "empty", "blank", "longest", "too-long", "nul", "not-text"],
)
def test_reject_note_is_optional_and_bounded(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    body: dict[str, Any] | None,
    status_code: int,
    note: str | None,
) -> None:
    change_set_key = _staged(session_factory, organisation_key, [_timeserie("a")])

    with _client(session_factory) as client:
        response = client.post(
            _url(organisation_key, change_set_key, "reject"), json=body
        )

    assert response.status_code == status_code
    stored = _stored(session_factory, change_set_key)
    assert stored.status == ("rejected" if status_code == 200 else "submitted")
    assert stored.review_note == note


def test_reject_of_a_draft_or_while_locked_changes_nothing(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    draft = _staged(session_factory, organisation_key, [_timeserie("a")], submit=False)
    submitted = _staged(session_factory, organisation_key, [_timeserie("b")])

    with _client(session_factory) as client:
        not_submitted = client.post(_url(organisation_key, draft, "reject"))

        def locked(*_args: object, **_kwargs: object) -> object:
            raise _lock_not_available()

        monkeypatch.setattr(engine, "get_active_organisation", locked)
        busy = client.post(_url(organisation_key, submitted, "reject"))

    assert not_submitted.status_code == 409
    assert _error_code(not_submitted) == "not_submitted"
    assert busy.status_code == 409
    assert _error_code(busy) == "apply_in_progress"
    assert _stored(session_factory, draft).status == "draft"
    stored = _stored(session_factory, submitted)
    assert (stored.status, stored.reviewed_by) == ("submitted", None)


def test_reject_while_the_database_is_unavailable_says_rejected(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key = _staged(session_factory, organisation_key, [_timeserie("a")])

    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise _query_cancelled()

    monkeypatch.setattr(engine, "get_active_organisation", unavailable)
    with _client(session_factory) as client:
        response = client.post(_url(organisation_key, change_set_key, "reject"))

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "apply_unavailable",
        "message": "The change set could not be rejected right now. Try again shortly.",
    }
    assert _stored(session_factory, change_set_key).status == "submitted"


def test_unparseable_operations_block_the_detail_but_not_reject(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _staged(session_factory, organisation_key, [_timeserie("a")])
    with session_factory() as session:
        row = session.scalar(
            select(AiChangeSetOperation).where(
                AiChangeSetOperation.change_set_id
                == _load(session, change_set_key).change_set_id
            )
        )
        assert row is not None
        # As if a later request-schema change no longer accepted the payload.
        row.payload = {**row.payload, "retired": True}
        session.commit()

    with _client(session_factory) as client:
        with pytest.raises(ValidationError):
            client.get(_url(organisation_key, change_set_key))
        listed = client.get(_url(organisation_key)).json()
        rejected = client.post(_url(organisation_key, change_set_key, "reject"))

    assert [item["id"] for item in listed] == [change_set_key]
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
