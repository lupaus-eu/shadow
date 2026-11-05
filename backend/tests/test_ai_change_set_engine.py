# pyright: reportPrivateUsage=false

import base64
import hashlib
import os

os.environ["APP_ENV"] = "test"
from collections.abc import Callable, Iterator, Sequence
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import psycopg
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import StaticPool, create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.ai_change_sets.engine as engine
from app.api.v1.ai_change_sets.models import AiChangeSet, AiChangeSetOperation
from app.api.v1.ai_change_sets.schemas import (
    OPERATION_ADAPTER,
    ChangeSetOperation,
    CreateEdgeOperation,
    CreateNodeOperation,
    ExecutionResult,
    NodeReplacement,
    PatchNodeOperation,
    ReplacementReport,
    TimeserieReplacement,
)
from app.api.v1.mcp_oauth.models import McpOauthClient, McpOauthGrant
from app.api.v1.mcp_oauth.service import approve_consent, start_authorization
from app.api.v1.mcp_oauth.token_service import (
    allowed_scopes_for_role,
    issue_tokens,
    revoke_connection,
)
from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import (
    DerivedMetricEquation,
    Event,
    OrgState,
    Scenario,
    Timeserie,
    TimeserieValue,
)
from app.api.v1.org_states.schemas import (
    ScenarioCreateRequest,
    TimeserieCreateRequest,
    TimeserieValueRequest,
    TimeserieValuesPatchRequest,
)
from app.api.v1.org_twin_structure import org_twin_structure_service
from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
    GraphEdge,
    GraphNode,
    Metamodel,
    NodeType,
)
from app.api.v1.org_twin_structure.schemas import GraphNodeCreateRequest
from app.api.v1.organisations import service as organisations_service
from app.api.v1.organisations.schemas import OrganisationCreateRequest
from app.api.v1.timeserie_generation.generator import GENERATOR_VERSION
from app.api.v1.users.models import User
from app.core.config import Settings
from app.core.models import Base

CREATOR_USER_ID = 7
REVIEWER_USER_ID = 8
SETTINGS = Settings.model_validate({"MCP_ENABLED": True})
BUSINESS_MODELS = (
    Scenario,
    OrgState,
    Event,
    Timeserie,
    TimeserieValue,
    DerivedMetricEquation,
    GraphNode,
    GraphEdge,
)
MONTHLY_SPEC: dict[str, Any] = {
    "startDate": "2026-01-01",
    "periods": 12,
    "timeUnit": "month",
    "baseLevel": 10,
    "trend": {"type": "linear", "slope": 1},
    "noise": {"std": 0.5},
    "seed": 7,
}
END_TO_END_OPERATIONS: list[dict[str, Any]] = [
    {"type": "create_scenario", "ref": "$plan", "payload": {"name": "AI plan"}},
    {
        "type": "create_org_state",
        "ref": "$start",
        "scenario_key": "$plan",
        "payload": {"name": "Plan start", "targetDate": "2026-01-01"},
    },
    {
        "type": "create_node",
        "scenario_key": "$plan",
        "org_state_key": "$start",
        "payload": {"id": "team_a", "name": "Team A", "nodeTypeId": "nt_person"},
    },
    {
        "type": "create_node",
        "scenario_key": "$plan",
        "org_state_key": "$start",
        "payload": {"id": "team_b", "name": "Team B", "nodeTypeId": "nt_person"},
    },
    {
        "type": "create_edge",
        "scenario_key": "$plan",
        "org_state_key": "$start",
        "payload": {
            "id": "a_reports_to_b",
            "name": "Reports to",
            "edgeTypeId": "et_reports_to",
            "sourceNodeId": "team_a",
            "targetNodeId": "team_b",
        },
    },
    {
        "type": "create_timeserie",
        "scenario_key": "$plan",
        "payload": {
            "id": "headcount",
            "name": "Headcount",
            "shortName": "headcount",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    },
    {
        "type": "generate_timeserie_values",
        "scenario_key": "$plan",
        "timeserie_key": "headcount",
        "spec": MONTHLY_SPEC,
    },
    {
        "type": "create_timeserie",
        "scenario_key": "$plan",
        "payload": {
            "id": "cost",
            "name": "Cost",
            "shortName": "cost",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    },
    {
        "type": "set_timeserie_values",
        "scenario_key": "$plan",
        "timeserie_key": "cost",
        "payload": {
            "values": [
                {"date": "2026-01-01", "value": 1000},
                {"date": "2026-02-01", "value": 1100},
            ]
        },
    },
    {
        "type": "create_derived_metric",
        "ref": "$cost_per_head",
        "scenario_key": "$plan",
        "payload": {"name": "Cost per head", "formula": "cost / headcount"},
    },
    {
        "type": "patch_node",
        "scenario_key": "$plan",
        "org_state_key": "$start",
        "node_key": "team_a",
        "payload": {"timeserieId": "$cost_per_head"},
    },
    {
        "type": "create_event",
        "ref": "$reorg",
        "scenario_key": "$plan",
        "payload": {"name": "Reorganisation", "targetDate": "2026-03-01"},
    },
]


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _factory(*, foreign_keys: bool = False) -> sessionmaker[Session]:
    sqlite: Engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    if foreign_keys:
        event.listen(sqlite, "connect", _enable_sqlite_foreign_keys)
    Base.metadata.create_all(sqlite)
    factory = sessionmaker(bind=sqlite, autocommit=False, autoflush=False)
    _seed_users_and_default_metamodel(factory)
    return factory


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    yield _factory()


@pytest.fixture()
def organisation_key(session_factory: sessionmaker[Session]) -> str:
    return _create_organisation(session_factory)


def _create_organisation(factory: sessionmaker[Session]) -> str:
    with factory() as session:
        return organisations_service.create_organisation(
            session,
            OrganisationCreateRequest(name="Acme Corp"),
            CREATOR_USER_ID,
        ).id


def _operations(raw: Sequence[dict[str, Any]]) -> list[ChangeSetOperation]:
    return [OPERATION_ADAPTER.validate_python(item) for item in raw]


def _create_change_set(
    factory: sessionmaker[Session],
    organisation_key: str,
    raw_operations: Sequence[dict[str, Any]] = (),
    *,
    grant_id: int | None = None,
) -> str:
    with factory() as session:
        change_set = engine.create_change_set(
            session,
            organisation_key,
            title="AI plan",
            rationale="Generated with the user.",
            created_by=CREATOR_USER_ID,
            grant_id=grant_id,
            client_id="client-1",
            client_name="Claude",
        )
        if raw_operations:
            engine.add_operations(
                session, change_set, _operations(raw_operations), CREATOR_USER_ID
            )
        session.commit()
        return change_set.change_set_key


def _load(session: Session, change_set_key: str) -> AiChangeSet:
    change_set = session.scalar(
        select(AiChangeSet).where(AiChangeSet.change_set_key == change_set_key)
    )
    assert change_set is not None
    return change_set


def _validate(factory: sessionmaker[Session], change_set_key: str) -> ExecutionResult:
    with factory() as session:
        result = engine.validate_change_set(
            session,
            factory,
            _load(session, change_set_key),
            CREATOR_USER_ID,
            settings=SETTINGS,
        )
        session.commit()
        return result


def _submit(factory: sessionmaker[Session], change_set_key: str) -> ExecutionResult:
    with factory() as session:
        result = engine.submit_change_set(
            session,
            factory,
            _load(session, change_set_key),
            CREATOR_USER_ID,
            settings=SETTINGS,
        )
        session.commit()
        return result


def _review(factory: sessionmaker[Session], change_set_key: str) -> ReplacementReport:
    with factory() as session:
        return engine.compute_replacements(
            session, _load(session, change_set_key), settings=SETTINGS
        )


def _apply(
    factory: sessionmaker[Session],
    organisation_key: str,
    change_set_key: str,
    fingerprint: str | None = None,
) -> ExecutionResult:
    if fingerprint is None:
        fingerprint = _review(factory, change_set_key).review_fingerprint
    with factory() as session:
        return engine.apply_change_set(
            session,
            organisation_key,
            change_set_key,
            fingerprint,
            REVIEWER_USER_ID,
            channel=engine.ReviewChannel.web(),
            settings=SETTINGS,
        )


def _apply_error(
    factory: sessionmaker[Session],
    organisation_key: str,
    change_set_key: str,
    fingerprint: str | None = None,
) -> engine.ChangeSetApplyError:
    with pytest.raises(engine.ChangeSetApplyError) as error:
        _apply(factory, organisation_key, change_set_key, fingerprint)
    return error.value


def _status(factory: sessionmaker[Session], change_set_key: str) -> AiChangeSet:
    with factory() as session:
        change_set = _load(session, change_set_key)
        session.expunge(change_set)
        return change_set


def _row_counts(factory: sessionmaker[Session]) -> dict[str, int]:
    with factory() as session:
        return {
            model.__tablename__: session.scalar(
                select(func.count()).select_from(model),
            )
            or 0
            for model in BUSINESS_MODELS
        }


def _statuses(result: ExecutionResult) -> list[str]:
    return [item.status for item in result.operations]


def _values(
    factory: sessionmaker[Session],
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
) -> list[tuple[date, object]]:
    with factory() as session:
        timeserie = org_states_service.get_timeserie(
            session, organisation_key, scenario_key, timeserie_key
        )
    return [(value.date, value.value) for value in timeserie.values]


def _create_timeserie(
    factory: sessionmaker[Session],
    organisation_key: str,
    key: str,
    values: Sequence[tuple[date, float]] = (),
    *,
    scenario_key: str = "reality",
) -> None:
    with factory() as session:
        org_states_service.create_timeserie(
            session,
            organisation_key,
            scenario_key,
            TimeserieCreateRequest(
                id=key, name=key.title(), timeUnit="month", valueUnit="number"
            ),
            CREATOR_USER_ID,
        )
    if values:
        _replace_values(factory, organisation_key, key, values, scenario_key)


def _replace_values(
    factory: sessionmaker[Session],
    organisation_key: str,
    key: str,
    values: Sequence[tuple[date, float]],
    scenario_key: str = "reality",
) -> None:
    with factory() as session:
        org_states_service.replace_timeserie_values(
            session,
            organisation_key,
            scenario_key,
            key,
            TimeserieValuesPatchRequest(
                values=[
                    TimeserieValueRequest(date=value_date, value=value)
                    for value_date, value in values
                ]
            ),
            CREATOR_USER_ID,
        )


def _create_node(
    factory: sessionmaker[Session], organisation_key: str, key: str, name: str
) -> None:
    with factory() as session:
        org_twin_structure_service.create_graph_node(
            session,
            organisation_key,
            "reality",
            "initial_state",
            GraphNodeCreateRequest(id=key, name=name, nodeTypeId="nt_person"),
            CREATOR_USER_ID,
        )


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


def test_end_to_end_change_set_dry_runs_without_persisting_rows(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS
    )
    baseline = _row_counts(session_factory)

    result = _validate(session_factory, change_set_key)

    assert result.ok, result.operations
    assert _statuses(result) == ["ok"] * len(END_TO_END_OPERATIONS)
    assert set(result.refs) == {"$plan", "$start", "$cost_per_head", "$reorg"}
    assert result.operations[2].key == "team_a"
    assert result.operations[0].scenario_key == result.refs["$plan"]
    assert _row_counts(session_factory) == baseline
    change_set = _status(session_factory, change_set_key)
    assert change_set.status == "draft"
    assert change_set.validation_result == result.model_dump(mode="json")


def test_dry_run_guard_rejects_a_commit_and_rolls_back(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_scenario = org_states_service.create_scenario_in_transaction

    def committing_core(
        session: Session,
        organisation_key: str,
        payload: ScenarioCreateRequest,
        actor_user_id: int,
    ) -> Scenario:
        scenario = create_scenario(session, organisation_key, payload, actor_user_id)
        session.commit()
        return scenario

    monkeypatch.setattr(
        org_states_service, "create_scenario_in_transaction", committing_core
    )
    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:2]
    )
    baseline = _row_counts(session_factory)

    with pytest.raises(engine.DryRunCommitError):
        _validate(session_factory, change_set_key)

    assert _row_counts(session_factory) == baseline


def test_end_to_end_change_set_applies_atomically_with_frozen_values(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS
    )
    submitted = _submit(session_factory, change_set_key)
    assert submitted.ok
    with session_factory() as session:
        change_set = _load(session, change_set_key)
        assert change_set.status == "submitted"
        frozen_rows = session.scalars(
            select(AiChangeSetOperation).where(
                AiChangeSetOperation.frozen_values.is_not(None)
            )
        ).all()
        assert [row.op_type for row in frozen_rows] == ["generate_timeserie_values"]
        frozen = frozen_rows[0].frozen_values
        assert frozen is not None
        assert frozen["generatorVersion"] == GENERATOR_VERSION
        assert len(frozen["values"]) == 12

    def regenerate(*_args: object) -> object:
        raise AssertionError("apply must use the frozen values")

    monkeypatch.setattr(engine, "generate", regenerate)
    review = _review(session_factory, change_set_key)
    assert not any(item.replaces_existing for item in review.operations)

    result = _apply(
        session_factory, organisation_key, change_set_key, review.review_fingerprint
    )

    assert result.ok
    plan_key = result.refs["$plan"]
    assert _values(session_factory, organisation_key, plan_key, "headcount") == [
        (date.fromisoformat(point["date"]), point["value"])
        for point in frozen["values"]
    ]
    with session_factory() as session:
        scenario = session.scalar(
            select(Scenario).where(Scenario.scenario_key == plan_key)
        )
        assert scenario is not None
        assert scenario.created_by == REVIEWER_USER_ID
        node = session.scalar(select(GraphNode).where(GraphNode.node_key == "team_a"))
        assert node is not None
        derived = session.get(Timeserie, node.timeserie_id)
        assert derived is not None
        assert derived.timeserie_key == result.refs["$cost_per_head"]
        edge = session.scalar(select(GraphEdge))
        assert edge is not None and edge.edge_key == "a_reports_to_b"
        assert (
            session.scalar(
                select(Event.event_key).where(Event.scenario_id == scenario.scenario_id)
            )
            == (result.refs["$reorg"])
        )
        change_set = _load(session, change_set_key)
        assert change_set.status == "applied"
        assert change_set.reviewed_by == REVIEWER_USER_ID
        assert change_set.reviewed_time is not None
        assert change_set.created_by == CREATOR_USER_ID
        assert change_set.applied_result is not None
        assert change_set.applied_result["status"] == "applied"
        assert change_set.applied_result["refs"] == result.refs


def test_a_failing_operation_in_the_middle_persists_nothing(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    operations: list[dict[str, Any]] = [
        {
            "type": "create_timeserie",
            "scenario_key": "reality",
            "payload": {
                "id": key,
                "name": key.title(),
                "timeUnit": "month",
                "valueUnit": "number",
            },
        }
        for key in ("alpha", "beta")
    ] + [
        {
            "type": "create_node",
            "scenario_key": "reality",
            "org_state_key": "initial_state",
            "payload": {"id": "hq", "name": "HQ", "nodeTypeId": "nt_person"},
        }
    ]
    change_set_key = _create_change_set(session_factory, organisation_key, operations)
    assert _submit(session_factory, change_set_key).ok
    # A human creates "beta" through REST after submit.
    _create_timeserie(session_factory, organisation_key, "beta")
    baseline = _row_counts(session_factory)

    error = _apply_error(session_factory, organisation_key, change_set_key)

    assert error.code == "apply_failed"
    assert error.step == "execute"
    assert error.change_set_status == "failed"
    assert error.outcome is not None
    assert [item.status for item in error.outcome.operations] == [
        "ok",
        "error",
        "not_run",
    ]
    assert all(item.key is None for item in error.outcome.operations)
    assert _row_counts(session_factory) == baseline
    with session_factory() as session:
        assert (
            session.scalar(select(Timeserie).where(Timeserie.timeserie_key == "alpha"))
            is None
        )
        change_set = _load(session, change_set_key)
        assert change_set.status == "failed"
        assert change_set.reviewed_by == REVIEWER_USER_ID
        assert change_set.applied_result is not None
        assert change_set.applied_result["step"] == "execute"
        assert change_set.applied_result["error"]["message"] == (
            "Operation 1: An active timeserie with this id already exists."
        )
        failing = session.scalar(
            select(AiChangeSetOperation).where(AiChangeSetOperation.position == 1)
        )
        assert failing is not None and failing.error is not None
        assert failing.error["code"] == "domain_error"


def test_dry_run_stops_at_the_first_failing_operation(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    operations = [
        *END_TO_END_OPERATIONS[:2],
        {
            "type": "create_node",
            "scenario_key": "$plan",
            "org_state_key": "$start",
            "payload": {"id": "ghost", "name": "Ghost", "nodeTypeId": "nt_missing"},
        },
        *END_TO_END_OPERATIONS[2:4],
    ]
    change_set_key = _create_change_set(session_factory, organisation_key, operations)
    baseline = _row_counts(session_factory)

    result = _validate(session_factory, change_set_key)

    assert not result.ok
    assert _statuses(result) == ["ok", "ok", "error", "not_run", "not_run"]
    error = result.operations[2].error
    assert error is not None
    assert (error.code, error.status_code) == ("domain_error", 404)
    assert _row_counts(session_factory) == baseline
    with session_factory() as session:
        rows = session.scalars(
            select(AiChangeSetOperation).order_by(AiChangeSetOperation.position)
        ).all()
        assert [row.error is not None for row in rows] == [
            False,
            False,
            True,
            False,
            False,
        ]
    # A failed validation leaves the change set a draft without frozen values.
    submitted = _submit(session_factory, change_set_key)
    assert not submitted.ok
    assert _status(session_factory, change_set_key).status == "draft"


def test_derived_scenario_key(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    with session_factory() as session:
        other_key = org_states_service.create_scenario(
            session,
            organisation_key,
            ScenarioCreateRequest(name="Other"),
            CREATOR_USER_ID,
        ).id

    def timeserie(scenario_key: str, key: str) -> dict[str, Any]:
        return {
            "type": "create_timeserie",
            "scenario_key": scenario_key,
            "payload": {
                "id": key,
                "name": key,
                "timeUnit": "month",
                "valueUnit": "number",
            },
        }

    single = _create_change_set(
        session_factory,
        organisation_key,
        [
            timeserie("reality", "alpha"),
            {
                "type": "create_node",
                "scenario_key": "reality",
                "org_state_key": "initial_state",
                "payload": {"id": "hq", "name": "HQ", "nodeTypeId": "nt_person"},
            },
            {
                "type": "create_event",
                "scenario_key": "reality",
                "payload": {"name": "Launch", "targetDate": "2026-01-01"},
            },
        ],
    )
    new_scenario = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS
    )
    several = _create_change_set(
        session_factory,
        organisation_key,
        [
            timeserie("reality", "alpha"),
            timeserie(other_key, "beta"),
            timeserie("reality", "delta"),
        ],
    )
    # Creating a scenario clears the reference even when every other operation
    # targets one existing scenario.
    created_beside = _create_change_set(
        session_factory,
        organisation_key,
        [END_TO_END_OPERATIONS[0], timeserie("reality", "alpha")],
    )
    empty = _create_change_set(session_factory, organisation_key)

    with session_factory() as session:
        keys = {
            name: engine.scenario_key_of(session, _load(session, key))
            for name, key in (
                ("single", single),
                ("new", new_scenario),
                ("several", several),
                ("created_beside", created_beside),
                ("empty", empty),
            )
        }
    assert keys == {
        "single": "reality",
        "new": None,
        "several": None,
        "created_beside": None,
        "empty": None,
    }

    # Removing the operation on the second scenario recomputes the reference.
    with session_factory() as session:
        change_set = _load(session, several)
        engine.remove_operation(session, change_set, 1, CREATOR_USER_ID)
        session.commit()
        assert engine.scenario_key_of(session, change_set) == "reality"
        engine.add_operations(
            session,
            change_set,
            _operations([timeserie(other_key, "gamma")]),
            CREATOR_USER_ID,
        )
        session.commit()
        assert engine.scenario_key_of(session, change_set) is None
        positions = session.scalars(
            select(AiChangeSetOperation.position)
            .where(AiChangeSetOperation.change_set_id == change_set.change_set_id)
            .order_by(AiChangeSetOperation.position)
        ).all()
        assert list(positions) == [0, 2, 3]


def test_copy_scenario_resolves_refs_and_clears_the_scenario_reference(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    timeserie_in_fork: dict[str, Any] = {
        "type": "create_timeserie",
        "scenario_key": "$fork",
        "payload": {
            "id": "headcount",
            "name": "Headcount",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    }
    operations: list[dict[str, Any]] = [
        {
            "type": "create_org_state",
            "ref": "$q2",
            "scenario_key": "reality",
            "payload": {"name": "Q2", "targetDate": "2026-04-01"},
        },
        {
            "type": "copy_scenario",
            "ref": "$fork",
            "payload": {
                "sourceScenarioId": "reality",
                "sourceOrgStateId": "$q2",
                "name": "Fork",
            },
        },
        timeserie_in_fork,
        *END_TO_END_OPERATIONS[:2],
        {
            "type": "copy_scenario",
            "payload": {"sourceScenarioId": "$plan", "sourceOrgStateId": "$start"},
        },
    ]
    change_set_key = _create_change_set(session_factory, organisation_key, operations)
    with session_factory() as session:
        assert engine.scenario_key_of(session, _load(session, change_set_key)) is None
    # A copy alone, from one existing scenario, has no scenario reference either.
    copy_only = _create_change_set(session_factory, organisation_key, operations[:2])
    with session_factory() as session:
        assert engine.scenario_key_of(session, _load(session, copy_only)) is None

    assert _statuses(_validate(session_factory, change_set_key)) == ["ok"] * 6
    assert _row_counts(session_factory)["scenarios"] == 1
    assert _submit(session_factory, change_set_key).ok
    report = _review(session_factory, change_set_key)
    assert [entry.replaces_existing for entry in report.operations] == [False] * 6

    result = _apply(session_factory, organisation_key, change_set_key)

    assert result.ok
    with session_factory() as session:
        names = set(
            session.scalars(
                select(Scenario.name).where(Scenario.deleted_time.is_(None))
            )
        )
        fork_timeseries = session.scalars(
            select(Timeserie.timeserie_key)
            .join(Scenario, Scenario.scenario_id == Timeserie.scenario_id)
            .where(Scenario.scenario_key == result.refs["$fork"])
        ).all()
    assert {"Fork", "AI plan", "Fork of AI plan"} <= names
    assert len(names) == 4
    assert list(fork_timeseries) == ["headcount"]

    # The source organisation state must belong to the source scenario.
    rejected = _create_change_set(session_factory, organisation_key)
    with session_factory() as session:
        with pytest.raises(HTTPException) as error:
            engine.add_operations(
                session,
                _load(session, rejected),
                _operations(
                    [
                        *END_TO_END_OPERATIONS[:2],
                        {
                            "type": "copy_scenario",
                            "payload": {
                                "sourceScenarioId": "reality",
                                "sourceOrgStateId": "$start",
                            },
                        },
                    ]
                ),
                CREATOR_USER_ID,
            )
    assert error.value.detail == (
        "Operation 2: payload.sourceOrgStateId uses $start, which belongs to "
        "scenario $plan, not reality."
    )


def _replacement_fixture(factory: sessionmaker[Session], organisation_key: str) -> str:
    _create_timeserie(
        factory,
        organisation_key,
        "revenue",
        [
            (date(2026, 1, 1), 100.0),
            (date(2026, 2, 1), 110.0),
            (date(2026, 3, 1), 120.0),
        ],
    )
    _create_timeserie(factory, organisation_key, "empty")
    _create_node(factory, organisation_key, "hq", "HQ")
    spec = {**MONTHLY_SPEC, "periods": 3, "noise": None}
    return _create_change_set(
        factory,
        organisation_key,
        [
            {
                "type": "patch_node",
                "scenario_key": "reality",
                "org_state_key": "initial_state",
                "node_key": "hq",
                "payload": {"name": "Head office", "attributes": {"city": "Oulu"}},
            },
            {
                "type": "set_timeserie_values",
                "scenario_key": "reality",
                "timeserie_key": "revenue",
                "payload": {"values": [{"date": "2026-01-01", "value": 1}]},
            },
            {
                "type": "generate_timeserie_values",
                "scenario_key": "reality",
                "timeserie_key": "empty",
                "spec": spec,
            },
            {
                "type": "create_node",
                "scenario_key": "reality",
                "org_state_key": "initial_state",
                "payload": {"id": "lab", "name": "Lab", "nodeTypeId": "nt_person"},
            },
            {
                "type": "patch_node",
                "scenario_key": "reality",
                "org_state_key": "initial_state",
                "node_key": "lab",
                "payload": {"name": "Research lab"},
            },
            {
                "type": "create_timeserie",
                "scenario_key": "reality",
                "payload": {
                    "id": "fresh",
                    "name": "Fresh",
                    "timeUnit": "month",
                    "valueUnit": "number",
                },
            },
            {
                "type": "generate_timeserie_values",
                "scenario_key": "reality",
                "timeserie_key": "fresh",
                "spec": spec,
            },
            {
                "type": "create_org_state",
                "ref": "$q2",
                "scenario_key": "reality",
                "payload": {"name": "Q2", "targetDate": "2026-04-01"},
            },
            {
                "type": "patch_node",
                "scenario_key": "reality",
                "org_state_key": "$q2",
                "node_key": "hq",
                "payload": {"description": "Moved"},
            },
        ],
    )


def test_replacement_flags_are_computed_against_current_data(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _replacement_fixture(session_factory, organisation_key)
    assert _submit(session_factory, change_set_key).ok

    review = _review(session_factory, change_set_key)

    flags = [item.replaces_existing for item in review.operations]
    assert flags == [True, True, False, False, False, False, False, False, True]
    node = review.operations[0].summary
    assert isinstance(node, NodeReplacement)
    assert node.fields == {"attributes": {}, "name": "HQ"}
    assert node.checksum is not None and not node.missing
    revenue = review.operations[1].summary
    assert isinstance(revenue, TimeserieReplacement)
    assert (revenue.value_count, revenue.first_date, revenue.last_date) == (
        3,
        date(2026, 1, 1),
        date(2026, 3, 1),
    )
    q2_node = review.operations[8].summary
    assert isinstance(q2_node, NodeReplacement)
    assert q2_node.fields == {"description": ""}
    # Recomputing unchanged data gives the same fingerprint.
    assert _review(session_factory, change_set_key) == review

    # A timeserie that gains values after submit is flagged on the next read.
    _replace_values(session_factory, organisation_key, "empty", [(date(2026, 1, 1), 5)])
    later = _review(session_factory, change_set_key)

    assert later.operations[2].replaces_existing
    empty = later.operations[2].summary
    assert isinstance(empty, TimeserieReplacement)
    assert empty.value_count == 1
    assert later.review_fingerprint != review.review_fingerprint


def test_apply_with_a_stale_fingerprint_changes_nothing(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _replacement_fixture(session_factory, organisation_key)
    assert _submit(session_factory, change_set_key).ok
    review = _review(session_factory, change_set_key)
    _replace_values(
        session_factory,
        organisation_key,
        "revenue",
        [(date(2026, 1, 1), 100.0), (date(2026, 2, 1), 110.0)],
    )
    baseline = _row_counts(session_factory)

    error = _apply_error(
        session_factory, organisation_key, change_set_key, review.review_fingerprint
    )

    assert (error.code, error.status_code, error.retryable) == (
        "review_stale",
        409,
        False,
    )
    assert error.step == "fingerprint"
    assert _row_counts(session_factory) == baseline
    assert _values(session_factory, organisation_key, "reality", "revenue") == [
        (date(2026, 1, 1), 100.0),
        (date(2026, 2, 1), 110.0),
    ]
    change_set = _status(session_factory, change_set_key)
    assert change_set.status == "submitted"
    assert change_set.applied_result is None
    assert change_set.reviewed_time is None


def test_editing_one_flagged_value_makes_the_review_stale(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _replacement_fixture(session_factory, organisation_key)
    assert _submit(session_factory, change_set_key).ok
    review = _review(session_factory, change_set_key)
    # Same count and date range, one value changed.
    _replace_values(
        session_factory,
        organisation_key,
        "revenue",
        [
            (date(2026, 1, 1), 100.0),
            (date(2026, 2, 1), 111.0),
            (date(2026, 3, 1), 120.0),
        ],
    )
    edited = _review(session_factory, change_set_key)
    summary = edited.operations[1].summary
    assert isinstance(summary, TimeserieReplacement)
    assert (summary.value_count, summary.first_date, summary.last_date) == (
        3,
        date(2026, 1, 1),
        date(2026, 3, 1),
    )

    error = _apply_error(
        session_factory, organisation_key, change_set_key, review.review_fingerprint
    )

    assert error.code == "review_stale"
    assert _status(session_factory, change_set_key).status == "submitted"
    # After reloading the review the reviewer can confirm again.
    result = _apply(
        session_factory, organisation_key, change_set_key, edited.review_fingerprint
    )
    assert result.ok
    assert _values(session_factory, organisation_key, "reality", "revenue") == [
        (date(2026, 1, 1), 1)
    ]
    with session_factory() as session:
        node = session.scalar(select(GraphNode).where(GraphNode.node_key == "hq"))
        assert node is not None
        assert node.name == "Head office"
        assert node.modified_by == REVIEWER_USER_ID


def test_a_target_deleted_after_submit_is_missing_and_fails_apply(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _replacement_fixture(session_factory, organisation_key)
    assert _submit(session_factory, change_set_key).ok
    with session_factory() as session:
        org_states_service.soft_delete_timeserie(
            session, organisation_key, "reality", "revenue", CREATOR_USER_ID
        )
    baseline = _row_counts(session_factory)

    review = _review(session_factory, change_set_key)

    summary = review.operations[1].summary
    assert isinstance(summary, TimeserieReplacement)
    assert summary.missing
    assert summary.message == "Timeserie not found."
    assert review.operations[1].replaces_existing

    error = _apply_error(
        session_factory, organisation_key, change_set_key, review.review_fingerprint
    )

    assert (error.code, error.step, error.change_set_status) == (
        "apply_failed",
        "execute",
        "failed",
    )
    assert error.message.endswith("Operation 1: Timeserie not found.")
    assert _row_counts(session_factory) == baseline
    with session_factory() as session:
        node = session.scalar(select(GraphNode).where(GraphNode.node_key == "hq"))
        assert node is not None and node.name == "HQ"


def test_review_stale_and_not_submitted_never_write_failed(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    draft_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:1]
    )
    error = _apply_error(session_factory, organisation_key, draft_key, "anything")
    assert (error.code, error.step, error.retryable) == (
        "not_submitted",
        "status",
        False,
    )
    assert _status(session_factory, draft_key).status == "draft"

    stale_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:1]
    )
    assert _submit(session_factory, stale_key).ok
    error = _apply_error(session_factory, organisation_key, stale_key, "stale")
    assert error.code == "review_stale"
    change_set = _status(session_factory, stale_key)
    assert (change_set.status, change_set.applied_result) == ("submitted", None)

    assert _apply(session_factory, organisation_key, stale_key).ok
    error = _apply_error(session_factory, organisation_key, stale_key, "anything")
    assert (error.code, error.change_set_status) == ("not_submitted", "applied")
    assert _status(session_factory, stale_key).status == "applied"

    with pytest.raises(HTTPException) as missing:
        _apply(session_factory, organisation_key, "change_set_unknown", "anything")
    assert missing.value.status_code == 404


@pytest.mark.parametrize(
    ("target", "step", "raised", "code"),
    [
        ("compute_replacements", "fingerprint", _query_cancelled, "apply_unavailable"),
        # Only the lock step maps the lock-not-available error to in-progress.
        (
            "compute_replacements",
            "fingerprint",
            _lock_not_available,
            "apply_unavailable",
        ),
        ("get_active_organisation", "lock", _lock_not_available, "apply_in_progress"),
        ("get_active_organisation", "lock", _query_cancelled, "apply_unavailable"),
    ],
)
def test_pre_execution_errors_are_retryable_and_keep_submitted(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    step: str,
    raised: Any,
    code: str,
) -> None:
    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:1]
    )
    assert _submit(session_factory, change_set_key).ok
    fingerprint = _review(session_factory, change_set_key).review_fingerprint

    def fail(*_args: object, **_kwargs: object) -> object:
        raise raised()

    monkeypatch.setattr(engine, target, fail)
    error = _apply_error(session_factory, organisation_key, change_set_key, fingerprint)

    assert (error.code, error.step, error.retryable) == (code, step, True)
    assert error.status_code == (503 if code == "apply_unavailable" else 409)
    assert isinstance(error.__cause__, OperationalError)
    change_set = _status(session_factory, change_set_key)
    assert (change_set.status, change_set.applied_result) == ("submitted", None)


def test_a_commit_failure_marks_the_change_set_failed(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:1]
    )
    assert _submit(session_factory, change_set_key).ok
    fingerprint = _review(session_factory, change_set_key).review_fingerprint
    baseline = _row_counts(session_factory)
    commit = Session.commit
    calls: list[int] = []

    def fail_first_commit(self: Session) -> None:
        calls.append(1)
        if len(calls) == 1:
            raise _query_cancelled()
        commit(self)

    monkeypatch.setattr(Session, "commit", fail_first_commit)
    error = _apply_error(session_factory, organisation_key, change_set_key, fingerprint)
    monkeypatch.undo()

    assert (error.code, error.step, error.change_set_status) == (
        "apply_failed",
        "commit",
        "failed",
    )
    assert error.outcome is not None and error.outcome.error is not None
    assert error.outcome.error.code == "statement_timeout"
    assert _row_counts(session_factory) == baseline
    assert _status(session_factory, change_set_key).status == "failed"


def test_settings_require_statement_timeout_longer_than_lock_timeout() -> None:
    for statement_timeout, lock_timeout in ((5_000, 5_000), (4_000, 5_000)):
        with pytest.raises(ValidationError, match="must be longer than"):
            Settings.model_validate(
                {
                    "AI_CHANGE_SET_STATEMENT_TIMEOUT_MS": statement_timeout,
                    "AI_CHANGE_SET_LOCK_TIMEOUT_MS": lock_timeout,
                }
            )
    settings = Settings.model_validate(
        {
            "AI_CHANGE_SET_STATEMENT_TIMEOUT_MS": 5_001,
            "AI_CHANGE_SET_LOCK_TIMEOUT_MS": 5_000,
        }
    )
    assert settings.ai_change_set_statement_timeout_ms == 5_001
    defaults = Settings.model_validate({})
    assert (
        defaults.ai_change_set_statement_timeout_ms,
        defaults.ai_change_set_lock_timeout_ms,
    ) == (30_000, 5_000)


def test_lazy_cleanup_nulls_the_grant_and_keeps_the_audit_record() -> None:
    factory = _factory(foreign_keys=True)
    organisation_key = _create_organisation(factory)
    redirect_uri = "http://localhost:33418/callback"
    resource = "http://testserver/api/mcp"
    verifier = "v" * 64
    with factory() as session:
        session.add(
            McpOauthClient(
                client_id="client-1", client_name="Claude", redirect_uris=[redirect_uri]
            )
        )
        session.commit()

    def token_request() -> None:
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        with factory() as session:
            location = start_authorization(
                session,
                SETTINGS,
                {
                    "response_type": ["code"],
                    "client_id": ["client-1"],
                    "redirect_uri": [redirect_uri],
                    "code_challenge": [challenge],
                    "code_challenge_method": ["S256"],
                    "scope": ["schatten.read schatten.write"],
                    "resource": [resource],
                },
            )
        with factory() as session:
            redirect = approve_consent(
                session,
                SETTINGS,
                dict(parse_qsl(urlsplit(location).query))["request"],
                user_id=CREATOR_USER_ID,
                allowed_scopes=allowed_scopes_for_role("consultant"),
            )
        with factory() as session:
            issued = issue_tokens(
                session,
                SETTINGS,
                {
                    "grant_type": ["authorization_code"],
                    "code": [dict(parse_qsl(urlsplit(redirect).query))["code"]],
                    "client_id": ["client-1"],
                    "redirect_uri": [redirect_uri],
                    "code_verifier": [verifier],
                    "resource": [resource],
                },
            )
        assert issued.access_token

    token_request()
    with factory() as session:
        grant = session.scalar(select(McpOauthGrant))
        assert grant is not None
        assert (grant.resource, grant.scopes) == (
            resource,
            "schatten.read schatten.write",
        )
        grant_id, grant_key = grant.grant_id, grant.grant_key
    change_set_key = _create_change_set(
        factory, organisation_key, END_TO_END_OPERATIONS[:1], grant_id=grant_id
    )
    with factory() as session:
        revoke_connection(session, grant_key, user_id=CREATOR_USER_ID)

    # The next token request's lazy cleanup deletes the revoked grant.
    token_request()

    with factory() as session:
        grants = session.scalars(select(McpOauthGrant)).all()
        assert [item.grant_key for item in grants] != [grant_key]
        assert all(item.revoked_time is None for item in grants)
        change_set = _load(session, change_set_key)
        assert change_set.grant_id is None
        assert (
            change_set.created_by,
            change_set.client_id,
            change_set.client_name,
        ) == (CREATOR_USER_ID, "client-1", "Claude")
        assert session.scalar(select(func.count()).select_from(AiChangeSetOperation))


def test_refs_only_name_server_generated_keys() -> None:
    def rejected(raw: dict[str, Any]) -> str:
        with pytest.raises(ValidationError) as error:
            OPERATION_ADAPTER.validate_python(raw)
        return str(error.value)

    node: dict[str, Any] = {
        "type": "create_node",
        "scenario_key": "reality",
        "org_state_key": "initial_state",
        "payload": {"id": "hq", "name": "HQ", "nodeTypeId": "nt_person"},
    }
    assert "Extra inputs are not permitted" in rejected({**node, "ref": "$hq"})
    assert "must not start with $" in rejected(
        {**node, "payload": {**node["payload"], "id": "$hq"}}
    )
    assert "must not start with $" in rejected(
        {
            "type": "create_edge",
            "scenario_key": "reality",
            "org_state_key": "initial_state",
            "payload": {
                "id": "edge",
                "name": "Edge",
                "edgeTypeId": "et_reports_to",
                "sourceNodeId": "$hq",
                "targetNodeId": "lab",
            },
        }
    )
    assert "must not start with $" in rejected(
        {
            "type": "set_timeserie_values",
            "scenario_key": "reality",
            "timeserie_key": "$revenue",
            "payload": {"values": []},
        }
    )
    assert "must not start with $" in rejected(
        {
            "type": "create_timeserie",
            "scenario_key": "reality",
            "payload": {
                "id": "$revenue",
                "name": "Revenue",
                "timeUnit": "month",
                "valueUnit": "number",
            },
        }
    )
    assert "is not a valid $ref symbol" in rejected({**node, "scenario_key": "$1"})
    assert "Provide at least one graph node field" in rejected(
        {
            "type": "patch_node",
            "scenario_key": "reality",
            "org_state_key": "initial_state",
            "node_key": "hq",
            "payload": {},
        }
    )


def test_graph_names_and_keys_have_length_limits() -> None:
    def rejected(raw: dict[str, Any]) -> str:
        with pytest.raises(ValidationError) as error:
            OPERATION_ADAPTER.validate_python(raw)
        return str(error.value)

    too_long = "N" * 61
    node: dict[str, Any] = {
        "type": "create_node",
        "scenario_key": "reality",
        "org_state_key": "initial_state",
        "payload": {"id": "hq", "name": "N" * 60, "nodeTypeId": "nt_person"},
    }
    edge: dict[str, Any] = {
        "type": "create_edge",
        "scenario_key": "reality",
        "org_state_key": "initial_state",
        "payload": {
            "id": "edge",
            "name": "N" * 60,
            "edgeTypeId": "et_reports_to",
            "sourceNodeId": "hq",
            "targetNodeId": "lab",
        },
    }
    OPERATION_ADAPTER.validate_python(node)
    OPERATION_ADAPTER.validate_python(edge)

    message = "Name must be at most 60 characters."
    assert message in rejected(
        {**node, "payload": {**node["payload"], "name": too_long}}
    )
    assert message in rejected(
        {**edge, "payload": {**edge["payload"], "name": too_long}}
    )
    assert message in rejected(
        {
            "type": "patch_node",
            "scenario_key": "reality",
            "org_state_key": "initial_state",
            "node_key": "hq",
            "payload": {"name": too_long},
        }
    )
    assert "at most 128 characters" in rejected(
        {**node, "payload": {**node["payload"], "id": "n" * 129}}
    )
    assert "at most 128 characters" in rejected(
        {**edge, "payload": {**edge["payload"], "id": "e" * 129}}
    )

    # Rows staged before the limits stay readable, like other stored names.
    stored_payloads: dict[str, dict[str, Any]] = {
        "create_node": {
            **node["payload"],
            "id": "n" * 129,
            "name": too_long,
        },
        "create_edge": {**edge["payload"], "id": "e" * 129, "name": too_long},
        "patch_node": {"name": too_long},
    }
    for op_type, payload in stored_payloads.items():
        row = AiChangeSetOperation(
            position=0,
            op_type=op_type,
            payload={
                "scenario_key": "reality",
                "org_state_key": "initial_state",
                **({"node_key": "hq"} if op_type == "patch_node" else {}),
                "payload": payload,
            },
        )
        operation = engine.staged_operation(row).operation
        assert isinstance(
            operation, CreateNodeOperation | CreateEdgeOperation | PatchNodeOperation
        )
        assert operation.payload.name == too_long


def test_change_set_staged_before_the_name_limits_still_applies(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:5]
    )
    long_name = "N" * 61
    node_key = "n" * 129
    edge_key = "e" * 129

    # Rewrite the stored rows as a change set staged before the limits looks.
    with session_factory() as session:
        rows = session.scalars(
            select(AiChangeSetOperation).order_by(AiChangeSetOperation.position)
        ).all()
        node_row, edge_row = rows[2], rows[4]
        assert (node_row.op_type, edge_row.op_type) == ("create_node", "create_edge")
        node_row.payload = {
            **node_row.payload,
            "payload": {
                **node_row.payload["payload"],
                "id": node_key,
                "name": long_name,
            },
        }
        edge_row.payload = {
            **edge_row.payload,
            "payload": {
                **edge_row.payload["payload"],
                "id": edge_key,
                "name": long_name,
                "sourceNodeId": node_key,
            },
        }
        session.commit()

    # A new operation is still checked strictly; a valid one joins the old rows.
    too_long_node: dict[str, Any] = {
        "type": "create_node",
        "scenario_key": "$plan",
        "org_state_key": "$start",
        "payload": {"id": "team_c", "name": long_name, "nodeTypeId": "nt_person"},
    }
    with pytest.raises(ValidationError, match="Name must be at most 60 characters."):
        _operations([too_long_node])
    with session_factory() as session:
        engine.add_operations(
            session,
            _load(session, change_set_key),
            _operations(
                [
                    {
                        **too_long_node,
                        "payload": {**too_long_node["payload"], "name": "C"},
                    }
                ]
            ),
            CREATOR_USER_ID,
        )
        session.commit()

    assert _validate(session_factory, change_set_key).ok
    assert _submit(session_factory, change_set_key).ok
    assert _apply(session_factory, organisation_key, change_set_key).ok

    with session_factory() as session:
        node = session.scalar(select(GraphNode).where(GraphNode.node_key == node_key))
        edge = session.scalar(select(GraphEdge).where(GraphEdge.edge_key == edge_key))
        assert node is not None
        assert edge is not None
        assert (node.name, edge.name) == (long_name, long_name)
        assert session.scalar(
            select(GraphNode).where(GraphNode.node_key == "team_c")
        ) is not None


def test_new_nodes_and_edges_are_referred_to_verbatim(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:5]
    )
    assert _submit(session_factory, change_set_key).ok

    result = _apply(session_factory, organisation_key, change_set_key)

    assert [item.key for item in result.operations[2:]] == [
        "team_a",
        "team_b",
        "a_reports_to_b",
    ]
    with session_factory() as session:
        edge = session.scalar(select(GraphEdge))
        assert edge is not None
        source = session.get(GraphNode, edge.source_graph_node_id)
        assert source is not None and source.node_key == "team_a"


def test_reference_errors_are_clear(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    def add_error(raw: Sequence[dict[str, Any]]) -> HTTPException:
        change_set_key = _create_change_set(session_factory, organisation_key)
        with session_factory() as session:
            with pytest.raises(HTTPException) as error:
                engine.add_operations(
                    session,
                    _load(session, change_set_key),
                    _operations(raw),
                    CREATOR_USER_ID,
                )
        return error.value

    scenario, org_state = END_TO_END_OPERATIONS[:2]
    node = END_TO_END_OPERATIONS[2]

    undeclared = add_error([node])
    assert undeclared.status_code == 422
    assert undeclared.detail == (
        "Operation 0: scenario_key uses $plan, which no earlier operation declares."
    )
    # A symbol declared only by a later operation is not usable earlier.
    assert add_error([org_state, scenario]).detail == (
        "Operation 0: scenario_key uses $plan, which no earlier operation declares."
    )
    assert add_error([scenario, {**node, "org_state_key": "$plan"}]).detail == (
        "Operation 1: org_state_key uses $plan, which names a scenario created by "
        "operation 0; org_state_key needs an organisation state."
    )
    assert add_error(
        [scenario, org_state, {**node, "scenario_key": "reality"}]
    ).detail == (
        "Operation 2: org_state_key uses $start, which belongs to scenario $plan, "
        "not reality."
    )
    assert add_error([scenario, {**scenario, "payload": {"name": "Again"}}]).detail == (
        "Operation 1: ref $plan is already declared by operation 0."
    )
    assert add_error(
        [
            {
                "type": "create_event",
                "ref": "$launch",
                "scenario_key": "reality",
                "payload": {"name": "Launch", "targetDate": "2026-01-01"},
            },
            {
                "type": "patch_node",
                "scenario_key": "reality",
                "org_state_key": "initial_state",
                "node_key": "hq",
                "payload": {"timeserieId": "$launch"},
            },
        ]
    ).detail == (
        "Operation 1: payload.timeserieId uses $launch, which names an event created "
        "by operation 0; payload.timeserieId needs a derived metric."
    )

    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:3]
    )
    with session_factory() as session:
        with pytest.raises(HTTPException) as removal:
            engine.remove_operation(
                session, _load(session, change_set_key), 1, CREATOR_USER_ID
            )
    assert removal.value.status_code == 409
    assert removal.value.detail == (
        "Operation 1 cannot be removed. Operation 2: org_state_key uses $start, "
        "which no earlier operation declares."
    )

    # Execution reports an undeclared symbol as that operation's error.
    with session_factory() as session:
        organisation = organisations_service.get_active_organisation(
            session, organisation_key
        )
        result = engine.execute_operations(
            session,
            organisation,
            [engine.StagedOperation(0, operation) for operation in _operations([node])],
            CREATOR_USER_ID,
        )
        session.rollback()
    error = result.operations[0].error
    assert error is not None
    assert (error.code, error.message) == (
        "invalid_reference",
        "scenario_key uses $plan, which no earlier operation declares.",
    )


def test_only_drafts_can_be_changed(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:1]
    )
    assert _submit(session_factory, change_set_key).ok
    with session_factory() as session:
        change_set = _load(session, change_set_key)
        for change in (
            lambda: engine.add_operations(
                session,
                change_set,
                _operations(END_TO_END_OPERATIONS[1:2]),
                CREATOR_USER_ID,
            ),
            lambda: engine.remove_operation(session, change_set, 0, CREATOR_USER_ID),
            lambda: engine.validate_change_set(
                session, session_factory, change_set, CREATOR_USER_ID, settings=SETTINGS
            ),
        ):
            with pytest.raises(HTTPException) as error:
                change()
            assert error.value.status_code == 409


def test_validate_and_submit_refuse_unflushed_changes(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    change_set_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:1]
    )
    with session_factory() as session:
        change_set = _load(session, change_set_key)
        # Assigning the current value changes nothing and is allowed.
        change_set.title = change_set.title
        result = engine.validate_change_set(
            session, session_factory, change_set, CREATOR_USER_ID, settings=SETTINGS
        )
        assert _statuses(result) == ["ok"]
        session.commit()

        operation = session.scalars(
            select(AiChangeSetOperation).where(
                AiChangeSetOperation.change_set_id == change_set.change_set_id
            )
        ).one()
        # A changed, a new and a deleted object are each refused.
        pending_changes: list[Callable[[], object]] = [
            lambda: setattr(change_set, "title", "Renamed plan"),
            lambda: session.add(
                AiChangeSetOperation(
                    change_set_id=change_set.change_set_id,
                    position=1,
                    op_type="create_scenario",
                    payload={},
                )
            ),
            lambda: session.delete(operation),
        ]
        for make_pending_change in pending_changes:
            make_pending_change()
            for dry_run in (engine.validate_change_set, engine.submit_change_set):
                with pytest.raises(RuntimeError, match="commit the change-set edits"):
                    dry_run(
                        session,
                        session_factory,
                        change_set,
                        CREATOR_USER_ID,
                        settings=SETTINGS,
                    )
            session.rollback()

    stored = _status(session_factory, change_set_key)
    assert (stored.status, stored.title) == ("draft", "AI plan")
    with session_factory() as session:
        assert len(engine.load_operations(session, _load(session, change_set_key))) == 1


def test_limits_are_enforced(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    event_operation = {
        "type": "create_event",
        "scenario_key": "reality",
        "payload": {"name": "Launch", "targetDate": "2026-01-01"},
    }
    change_set_key = _create_change_set(
        session_factory, organisation_key, [event_operation] * 500
    )
    with session_factory() as session:
        change_set = _load(session, change_set_key)
        with pytest.raises(HTTPException) as too_many:
            engine.add_operations(
                session, change_set, _operations([event_operation]), CREATOR_USER_ID
            )
    assert too_many.value.status_code == 422
    assert too_many.value.detail == (
        "A change set has at most 500 operations; this one would have 501."
    )

    daily = {
        "type": "generate_timeserie_values",
        "scenario_key": "reality",
        "timeserie_key": "daily",
        "spec": {
            "startDate": "2026-01-01",
            "periods": 10_000,
            "timeUnit": "day",
            "baseLevel": 1,
            "seed": 1,
        },
    }
    values = {
        "type": "set_timeserie_values",
        "scenario_key": "reality",
        "timeserie_key": "daily",
        "payload": {"values": [{"date": "2026-01-01", "value": 1}]},
    }
    with_values = _create_change_set(session_factory, organisation_key, [daily, daily])
    with session_factory() as session:
        with pytest.raises(HTTPException) as too_many_values:
            engine.add_operations(
                session,
                _load(session, with_values),
                _operations([values]),
                CREATOR_USER_ID,
            )
    assert too_many_values.value.detail == (
        "A change set sets or generates at most 20000 timeserie values; this one "
        "would have 20001."
    )


def _seed_users_and_default_metamodel(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        session.add_all(
            [
                User(
                    user_id=CREATOR_USER_ID,
                    name="AI Creator",
                    email="creator@example.test",
                    role="consultant",
                ),
                User(
                    user_id=REVIEWER_USER_ID,
                    name="Reviewer",
                    email="reviewer@example.test",
                    role="admin",
                ),
            ]
        )
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
        edge_type = EdgeType(
            metamodel_id=metamodel.metamodel_id,
            edge_type_key="et_reports_to",
            name="Reports to",
            display_name="Reports to",
            ui_style="solid",
            ui_source_end="none",
            ui_target_end="arrow",
        )
        session.add_all([person_type, edge_type])
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


def test_apply_and_reject_record_their_review_channel(
    session_factory: sessionmaker[Session], organisation_key: str
) -> None:
    applied_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:1]
    )
    rejected_key = _create_change_set(
        session_factory, organisation_key, END_TO_END_OPERATIONS[:1]
    )
    for key in (applied_key, rejected_key):
        assert _submit(session_factory, key).ok
    fingerprint = _review(session_factory, applied_key).review_fingerprint

    with session_factory() as session:
        engine.apply_change_set(
            session,
            organisation_key,
            applied_key,
            fingerprint,
            REVIEWER_USER_ID,
            channel=engine.ReviewChannel.mcp("client-review", "Claude Code"),
            settings=SETTINGS,
        )
    with session_factory() as session:
        engine.reject_change_set(
            session,
            organisation_key,
            rejected_key,
            None,
            REVIEWER_USER_ID,
            channel=engine.ReviewChannel.web(),
            settings=SETTINGS,
        )
        session.commit()

    applied = _status(session_factory, applied_key)
    rejected = _status(session_factory, rejected_key)
    assert (
        applied.status,
        applied.reviewed_via,
        applied.review_client_id,
        applied.review_client_name,
    ) == ("applied", "mcp", "client-review", "Claude Code")
    assert (
        rejected.status,
        rejected.reviewed_via,
        rejected.review_client_id,
        rejected.review_client_name,
    ) == ("rejected", "web", None, None)


@pytest.mark.parametrize(
    "values",
    [
        # A review without its channel.
        {"reviewed_via": None},
        {"reviewed_via": "chat"},
        # The client belongs to an MCP review only, and needs both fields.
        {"review_client_id": "client-review", "review_client_name": "Claude"},
        {"reviewed_via": "mcp"},
        {"reviewed_via": "mcp", "review_client_id": "client-review"},
        {
            "reviewed_via": "mcp",
            "review_client_id": " ",
            "review_client_name": "Claude",
        },
        {
            "reviewed_via": "mcp",
            "review_client_id": "client-review",
            "review_client_name": "",
        },
    ],
)
def test_the_review_channel_constraints_hold(
    session_factory: sessionmaker[Session],
    organisation_key: str,
    values: dict[str, object],
) -> None:
    change_set_key = _create_change_set(session_factory, organisation_key)

    with session_factory() as session:
        change_set = _load(session, change_set_key)
        change_set.status = "rejected"
        change_set.reviewed_by = REVIEWER_USER_ID
        change_set.reviewed_time = change_set.created_time
        change_set.reviewed_via = "web"
        for name, value in values.items():
            setattr(change_set, name, value)
        with pytest.raises(IntegrityError):
            session.commit()
