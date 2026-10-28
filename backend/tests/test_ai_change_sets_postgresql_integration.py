# pyright: reportPrivateUsage=false

import os
import threading
import time
import uuid
from collections.abc import Callable, Generator, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote

import anyio
import psycopg
import pytest
from auth_helpers import authenticate_test_client
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastmcp import Client
from psycopg import sql
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.ai_change_sets.engine as engine
from app.api.v1.ai_change_sets.models import AiChangeSet
from app.api.v1.ai_change_sets.schemas import OPERATION_ADAPTER, ExecutionResult
from app.api.v1.mcp_oauth.models import McpOauthClient, McpOauthGrant
from app.api.v1.mcp_oauth.service import WRITE_SCOPE
from app.api.v1.mcp_oauth.token_service import McpPrincipal
from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import (
    OrgState,
    Scenario,
    Timeserie,
    TimeserieValue,
)
from app.api.v1.org_states.schemas import (
    OrgStateCreateRequest,
    ScenarioCreateRequest,
    TimeserieCreateRequest,
    TimeserieValueRequest,
    TimeserieValuesPatchRequest,
)
from app.api.v1.org_twin_structure import org_twin_structure_service
from app.api.v1.org_twin_structure.models import (
    AllowedConnection,
    EdgeType,
    GraphNode,
    Metamodel,
    NodeType,
)
from app.api.v1.org_twin_structure.schemas import GraphNodeCreateRequest
from app.api.v1.organisations import service as organisations_service
from app.api.v1.organisations.schemas import OrganisationCreateRequest
from app.api.v1.users.models import User
from app.core.config import Settings, get_sqlalchemy_database_url
from app.core.database import get_db_session
from app.core.migrations import UpCommand, execute_command
from app.main import create_app
from app.mcp.auth import current_principal
from app.mcp.runtime import McpToolRuntime
from app.mcp.write_server import build_write_server

TEST_DATABASE_ENV = "MIGRATION_TEST_DATABASE_URL"
CREATOR_USER_ID = 7
REVIEWER_USER_ID = 8
SHORT_TIMEOUTS = Settings.model_validate(
    {
        "AI_CHANGE_SET_LOCK_TIMEOUT_MS": 500,
        "AI_CHANGE_SET_STATEMENT_TIMEOUT_MS": 1_000,
    }
)
WAITING_TIMEOUTS = Settings.model_validate(
    {
        "AI_CHANGE_SET_LOCK_TIMEOUT_MS": 5_000,
        "AI_CHANGE_SET_STATEMENT_TIMEOUT_MS": 10_000,
    }
)


@pytest.fixture
def factory() -> Generator[sessionmaker[Session], None, None]:
    base_url = os.getenv(TEST_DATABASE_ENV)
    if base_url is None:
        pytest.skip(f"{TEST_DATABASE_ENV} is not configured")

    schema_name = f"ai_change_sets_test_{uuid.uuid4().hex}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )

    separator = "&" if "?" in base_url else "?"
    schema_url = f"{base_url}{separator}options={quote(f'-csearch_path={schema_name}')}"
    execute_command(UpCommand(), database_url=schema_url)
    settings = Settings(DATABASE_URL=schema_url)
    database = create_engine(get_sqlalchemy_database_url(settings))
    session_factory = sessionmaker(bind=database, autocommit=False, autoflush=False)
    _seed_users_and_default_metamodel(session_factory)
    try:
        yield session_factory
    finally:
        database.dispose()
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
            )


@pytest.fixture
def organisation_key(factory: sessionmaker[Session]) -> str:
    with factory() as session:
        return organisations_service.create_organisation(
            session, OrganisationCreateRequest(name="Acme Corp"), CREATOR_USER_ID
        ).id


def _timeserie_operation(key: str, name: str | None = None) -> dict[str, Any]:
    return {
        "type": "create_timeserie",
        "scenario_key": "reality",
        "payload": {
            "id": key,
            "name": name or key.title(),
            "timeUnit": "month",
            "valueUnit": "number",
        },
    }


def _create_change_set(
    factory: sessionmaker[Session],
    organisation_key: str,
    raw_operations: Sequence[dict[str, Any]],
) -> str:
    with factory() as session:
        change_set = engine.create_change_set(
            session,
            organisation_key,
            title="AI plan",
            rationale=None,
            created_by=CREATOR_USER_ID,
            grant_id=None,
            client_id="client-1",
            client_name="Claude",
        )
        engine.add_operations(
            session,
            change_set,
            [OPERATION_ADAPTER.validate_python(item) for item in raw_operations],
            CREATOR_USER_ID,
        )
        session.commit()
        return change_set.change_set_key


def _load(session: Session, change_set_key: str) -> AiChangeSet:
    change_set = session.scalar(
        select(AiChangeSet).where(AiChangeSet.change_set_key == change_set_key)
    )
    assert change_set is not None
    return change_set


def _submitted(
    factory: sessionmaker[Session],
    organisation_key: str,
    raw_operations: Sequence[dict[str, Any]],
) -> tuple[str, str]:
    """Create and submit a change set; return its key and review fingerprint."""
    change_set_key = _create_change_set(factory, organisation_key, raw_operations)
    with factory() as session:
        result = engine.submit_change_set(
            session,
            factory,
            _load(session, change_set_key),
            CREATOR_USER_ID,
            settings=WAITING_TIMEOUTS,
        )
        session.commit()
    assert result.ok, result.operations
    with factory() as session:
        report = engine.compute_replacements(
            session, _load(session, change_set_key), settings=WAITING_TIMEOUTS
        )
    return change_set_key, report.review_fingerprint


def _apply(
    factory: sessionmaker[Session],
    organisation_key: str,
    change_set_key: str,
    fingerprint: str,
    settings: Settings,
) -> ExecutionResult:
    with factory() as session:
        return engine.apply_change_set(
            session,
            organisation_key,
            change_set_key,
            fingerprint,
            REVIEWER_USER_ID,
            settings=settings,
        )


def _status(factory: sessionmaker[Session], change_set_key: str) -> str:
    with factory() as session:
        return _load(session, change_set_key).status


def _count(factory: sessionmaker[Session], model: type[Any], *where: Any) -> int:
    with factory() as session:
        return (
            session.scalar(select(func.count()).select_from(model).where(*where)) or 0
        )


def _in_thread(work: Callable[[], object]) -> tuple[threading.Thread, list[object]]:
    outcome: list[object] = []

    def run() -> None:
        try:
            outcome.append(work())
        except BaseException as exc:  # asserted by the caller
            outcome.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outcome


def _joined(thread: threading.Thread, outcome: list[object]) -> object:
    thread.join(timeout=15)
    assert not thread.is_alive()
    assert len(outcome) == 1
    return outcome[0]


def _wait_for_lock_waiter(factory: sessionmaker[Session]) -> None:
    """Wait until a transaction waits for a row of this schema's change sets.

    Only a transaction that waits for a row lock takes a tuple lock, and the
    regclass resolves through this test's search path.
    """
    deadline = time.monotonic() + 5
    with factory() as session:
        while time.monotonic() < deadline:
            waiting = session.scalar(
                text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'tuple' "
                    "AND relation = 'ai_change_sets'::regclass"
                )
            )
            session.rollback()
            if waiting:
                return
            time.sleep(0.02)
    raise AssertionError("no transaction waited for a lock")


def _skip_key_check(*_args: object) -> None:
    """Let a duplicate key reach the partial unique index."""


def _pause_first_call(
    monkeypatch: pytest.MonkeyPatch, module: object, name: str
) -> tuple[threading.Event, threading.Event]:
    """Pause the first call of `module.name` until `release` is set."""
    original = getattr(module, name)
    reached = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def paused(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        if len(calls) == 1:
            reached.set()
            assert release.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, paused)
    return reached, release


def test_lock_held_by_another_apply_returns_apply_in_progress(
    factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key, fingerprint = _submitted(
        factory, organisation_key, [_timeserie_operation("alpha")]
    )
    # The first apply holds the change-set lock while it computes the review.
    locked, release = _pause_first_call(monkeypatch, engine, "compute_replacements")
    first, first_outcome = _in_thread(
        lambda: _apply(
            factory, organisation_key, change_set_key, fingerprint, SHORT_TIMEOUTS
        )
    )
    try:
        assert locked.wait(timeout=5)
        started = time.monotonic()
        with pytest.raises(engine.ChangeSetApplyError) as error:
            _apply(
                factory, organisation_key, change_set_key, fingerprint, SHORT_TIMEOUTS
            )
        waited = time.monotonic() - started

        assert (error.value.code, error.value.step, error.value.retryable) == (
            "apply_in_progress",
            "lock",
            True,
        )
        assert error.value.status_code == 409
        assert 0.4 < waited < 3
        assert _status(factory, change_set_key) == "submitted"
    finally:
        release.set()
    result = _joined(first, first_outcome)
    assert isinstance(result, ExecutionResult) and result.ok
    assert _status(factory, change_set_key) == "applied"
    assert _count(factory, Timeserie, Timeserie.timeserie_key == "alpha") == 1


def test_lock_timeout_during_execution_marks_the_change_set_failed(
    factory: sessionmaker[Session], organisation_key: str
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
        org_states_service.replace_timeserie_values(
            session,
            organisation_key,
            "reality",
            "revenue",
            TimeserieValuesPatchRequest(
                values=[TimeserieValueRequest(date=date(2026, 1, 1), value=100)]
            ),
            CREATOR_USER_ID,
        )
    change_set_key, fingerprint = _submitted(
        factory,
        organisation_key,
        [
            _timeserie_operation("alpha"),
            {
                "type": "set_timeserie_values",
                "scenario_key": "reality",
                "timeserie_key": "revenue",
                "payload": {"values": [{"date": "2026-01-01", "value": 1}]},
            },
        ],
    )

    # A REST transaction holds the target timeserie row.
    with factory() as rest:
        rest.scalar(
            select(Timeserie)
            .where(Timeserie.timeserie_key == "revenue")
            .with_for_update()
        )
        with pytest.raises(engine.ChangeSetApplyError) as error:
            _apply(
                factory, organisation_key, change_set_key, fingerprint, SHORT_TIMEOUTS
            )
        rest.rollback()

    assert (error.value.code, error.value.step) == ("apply_failed", "execute")
    assert error.value.change_set_status == "failed"
    outcome = error.value.outcome
    assert outcome is not None and outcome.error is not None
    assert outcome.error.code == "lock_timeout"
    assert [item.status for item in outcome.operations] == ["ok", "error"]
    assert _status(factory, change_set_key) == "failed"
    assert _count(factory, Timeserie, Timeserie.timeserie_key == "alpha") == 0
    with factory() as session:
        value = session.scalar(select(TimeserieValue.value))
    assert value == {"value": 100}


def test_domain_cores_compose_and_roll_back_after_a_real_unique_index_conflict(
    factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-069B review F-001: the cores on the migrated PostgreSQL schema."""
    counted = (Scenario, OrgState, Timeserie, GraphNode)
    baseline = {model: _count(factory, model) for model in counted}

    with factory() as session:
        scenario = org_states_service.create_scenario_in_transaction(
            session, organisation_key, ScenarioCreateRequest(name="Plan"), 7
        )
        org_state = org_states_service.create_org_state_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            OrgStateCreateRequest(name="Start", targetDate=date(2026, 1, 1)),
            CREATOR_USER_ID,
        )
        org_twin_structure_service.create_graph_node_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            org_state.org_state_key,
            GraphNodeCreateRequest(id="hq", name="HQ", nodeTypeId="nt_person"),
            CREATOR_USER_ID,
        )
        org_states_service.create_timeserie_in_transaction(
            session,
            organisation_key,
            scenario.scenario_key,
            TimeserieCreateRequest(
                id="headcount", name="Headcount", timeUnit="month", valueUnit="number"
            ),
            CREATOR_USER_ID,
        )
        # Skip the key pre-check so the partial unique index itself rejects it.
        monkeypatch.setattr(
            org_states_service,
            "_ensure_timeserie_key_available",
            _skip_key_check,
        )
        with pytest.raises(HTTPException) as conflict:
            org_states_service.create_timeserie_in_transaction(
                session,
                organisation_key,
                scenario.scenario_key,
                TimeserieCreateRequest(
                    id="headcount",
                    name="Second headcount",
                    timeUnit="month",
                    valueUnit="number",
                ),
                CREATOR_USER_ID,
            )
        session.rollback()

    assert conflict.value.status_code == 409
    cause = conflict.value.__cause__
    assert isinstance(cause, IntegrityError)
    assert getattr(cause.orig, "sqlstate", None) == "23505"
    assert "ux_timeseries_scenario_key_active" in str(cause.orig)
    assert {model: _count(factory, model) for model in counted} == baseline


def test_dry_run_with_a_unique_violation_in_the_middle_persists_nothing(
    factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key = _create_change_set(
        factory,
        organisation_key,
        [
            _timeserie_operation("alpha"),
            _timeserie_operation("alpha", "Second alpha"),
            _timeserie_operation("beta"),
        ],
    )
    monkeypatch.setattr(
        org_states_service, "_ensure_timeserie_key_available", _skip_key_check
    )
    baseline = _count(factory, Timeserie)

    with factory() as session:
        result = engine.validate_change_set(
            session,
            factory,
            _load(session, change_set_key),
            CREATOR_USER_ID,
            settings=WAITING_TIMEOUTS,
        )
        session.commit()

    assert [item.status for item in result.operations] == ["ok", "error", "not_run"]
    error = result.operations[1].error
    assert error is not None
    assert (error.code, error.status_code) == ("domain_error", 409)
    assert _count(factory, Timeserie) == baseline
    with factory() as session:
        stored = _load(session, change_set_key)
        assert stored.status == "draft"
        assert stored.validation_result == result.model_dump(mode="json")


def test_concurrent_apply_applies_the_change_set_once(
    factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key, fingerprint = _submitted(
        factory,
        organisation_key,
        [
            {"type": "create_scenario", "ref": "$plan", "payload": {"name": "AI plan"}},
            {
                "type": "create_org_state",
                "scenario_key": "$plan",
                "payload": {"name": "Start", "targetDate": "2026-01-01"},
            },
        ],
    )
    locked, release = _pause_first_call(monkeypatch, engine, "compute_replacements")

    def apply() -> ExecutionResult:
        return _apply(
            factory, organisation_key, change_set_key, fingerprint, WAITING_TIMEOUTS
        )

    first, first_outcome = _in_thread(apply)
    try:
        assert locked.wait(timeout=5)
        second, second_outcome = _in_thread(apply)
        _wait_for_lock_waiter(factory)
    finally:
        release.set()

    outcomes = [_joined(first, first_outcome), _joined(second, second_outcome)]

    assert isinstance(outcomes[0], ExecutionResult) and outcomes[0].ok
    rejected = outcomes[1]
    assert isinstance(rejected, engine.ChangeSetApplyError)
    assert (rejected.code, rejected.change_set_status) == ("not_submitted", "applied")
    assert _count(factory, Scenario, Scenario.name == "AI plan") == 1
    assert _status(factory, change_set_key) == "applied"


def test_concurrent_apply_requests_apply_the_change_set_once(
    factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TASK-069K: two review API requests through a real connection pool."""
    change_set_key, fingerprint = _submitted(
        factory, organisation_key, [_timeserie_operation("alpha")]
    )
    app = create_app(settings=WAITING_TIMEOUTS)

    def override_get_db_session() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    url = (
        f"/api/v1/organisations/{organisation_key}/ai/change-sets/"
        f"{change_set_key}/apply"
    )
    locked, release = _pause_first_call(monkeypatch, engine, "compute_replacements")
    with TestClient(app) as first_client, TestClient(app) as second_client:
        authenticate_test_client(
            first_client, factory, user_id=REVIEWER_USER_ID, create_user=False
        )
        second_client.cookies.update(first_client.cookies)
        second_client.headers.update(
            {
                "Origin": first_client.headers["Origin"],
                "X-CSRF-Token": first_client.headers["X-CSRF-Token"],
            }
        )

        def apply(client: TestClient) -> Callable[[], tuple[int, Any]]:
            def post() -> tuple[int, Any]:
                response = client.post(url, json={"reviewFingerprint": fingerprint})
                return response.status_code, response.json()

            return post

        first, first_outcome = _in_thread(apply(first_client))
        try:
            assert locked.wait(timeout=5)
            second, second_outcome = _in_thread(apply(second_client))
            _wait_for_lock_waiter(factory)
        finally:
            release.set()
        applied = _joined(first, first_outcome)
        rejected = _joined(second, second_outcome)

    assert isinstance(applied, tuple) and isinstance(rejected, tuple)
    assert applied[0] == 200, applied
    assert applied[1]["changeSet"]["status"] == "applied"
    assert rejected[0] == 409, rejected
    assert rejected[1]["error"]["code"] == "not_submitted"
    assert _count(factory, Timeserie, Timeserie.timeserie_key == "alpha") == 1
    with factory() as session:
        change_set = _load(session, change_set_key)
        assert (change_set.status, change_set.reviewed_by) == (
            "applied",
            REVIEWER_USER_ID,
        )


def test_a_transient_failure_never_overwrites_a_concurrent_successful_apply(
    factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key, fingerprint = _submitted(
        factory, organisation_key, [_timeserie_operation("alpha")]
    )
    create_timeserie = org_states_service.create_timeserie_in_transaction
    calls: list[int] = []

    def slow_in_first_apply(session: Session, *args: Any) -> Timeserie:
        calls.append(1)
        if len(calls) == 1:
            session.execute(text("SELECT pg_sleep(5)"))
        return create_timeserie(session, *args)

    monkeypatch.setattr(
        org_states_service, "create_timeserie_in_transaction", slow_in_first_apply
    )
    # Hold the first apply after its rollback, before it marks the change set
    # failed, until the second apply has succeeded.
    rolled_back, release = _pause_first_call(monkeypatch, engine, "_mark_failed")

    first, first_outcome = _in_thread(
        lambda: _apply(
            factory, organisation_key, change_set_key, fingerprint, SHORT_TIMEOUTS
        )
    )
    try:
        assert rolled_back.wait(timeout=10)
        assert _status(factory, change_set_key) == "submitted"
        second = _apply(
            factory, organisation_key, change_set_key, fingerprint, WAITING_TIMEOUTS
        )
    finally:
        release.set()
    failed = _joined(first, first_outcome)

    assert second.ok
    assert isinstance(failed, engine.ChangeSetApplyError)
    assert (failed.code, failed.step) == ("apply_failed", "execute")
    assert failed.outcome is not None and failed.outcome.error is not None
    assert failed.outcome.error.code == "statement_timeout"
    assert failed.change_set_status == "applied"
    with factory() as session:
        change_set = _load(session, change_set_key)
        assert change_set.status == "applied"
        assert change_set.applied_result is not None
        assert change_set.applied_result["status"] == "applied"
    assert _count(factory, Timeserie, Timeserie.timeserie_key == "alpha") == 1


def test_validate_or_submit_after_an_edit_in_the_same_transaction_is_refused(
    factory: sessionmaker[Session], organisation_key: str
) -> None:
    """The dry-run would wait for the edit's key-share lock on its scenario row."""
    org_state: dict[str, Any] = {
        "type": "create_org_state",
        "scenario_key": "reality",
        "payload": {"name": "Q2", "targetDate": "2026-04-01"},
    }
    with factory() as session:
        change_set = engine.create_change_set(
            session,
            organisation_key,
            title="AI plan",
            rationale=None,
            created_by=CREATOR_USER_ID,
            grant_id=None,
            client_id="client-1",
            client_name="Claude",
        )
        session.commit()
        engine.add_operations(
            session,
            change_set,
            [OPERATION_ADAPTER.validate_python(org_state)],
            CREATOR_USER_ID,
        )
        started = time.monotonic()
        for dry_run in (engine.validate_change_set, engine.submit_change_set):
            with pytest.raises(RuntimeError, match="commit the change-set edits"):
                dry_run(
                    session,
                    factory,
                    change_set,
                    CREATOR_USER_ID,
                    settings=SHORT_TIMEOUTS,
                )
        assert time.monotonic() - started < 0.5

        session.commit()
        result = engine.submit_change_set(
            session, factory, change_set, CREATOR_USER_ID, settings=SHORT_TIMEOUTS
        )
        session.commit()
        change_set_key = change_set.change_set_key

    assert result.ok
    assert _status(factory, change_set_key) == "submitted"
    assert _count(factory, OrgState, OrgState.name == "Q2") == 0


def test_dry_run_and_review_run_under_the_statement_timeout(
    factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    change_set_key = _create_change_set(
        factory, organisation_key, [_timeserie_operation("alpha")]
    )
    create_timeserie = org_states_service.create_timeserie_in_transaction

    def slow(session: Session, *args: Any) -> Timeserie:
        session.execute(text("SELECT pg_sleep(3)"))
        return create_timeserie(session, *args)

    monkeypatch.setattr(org_states_service, "create_timeserie_in_transaction", slow)
    with factory() as session:
        result = engine.validate_change_set(
            session,
            factory,
            _load(session, change_set_key),
            CREATOR_USER_ID,
            settings=SHORT_TIMEOUTS,
        )
        session.commit()

    error = result.operations[0].error
    assert error is not None and error.code == "statement_timeout"
    assert _status(factory, change_set_key) == "draft"

    # The review detail reads under the same timeout outside apply.
    with factory() as session:
        engine.compute_replacements(
            session, _load(session, change_set_key), settings=SHORT_TIMEOUTS
        )
        assert session.scalar(text("SHOW statement_timeout")) == "1s"


def test_write_tools_stage_and_submit_through_a_real_connection_pool(
    factory: sessionmaker[Session], organisation_key: str
) -> None:
    """The tools commit edits before the dry-run takes its own connection.

    `create_org_state` locks its scenario row for update, which an uncommitted
    edit's key-share lock on that row would block until the statement timeout.
    """
    principal = _write_principal(factory)
    server = build_write_server(
        McpToolRuntime(factory, anyio.CapacityLimiter(4)), SHORT_TIMEOUTS
    )
    operations: list[dict[str, Any]] = [
        {
            "type": "create_org_state",
            "ref": "$q2",
            "scenario_key": "reality",
            "payload": {"name": "Q2", "targetDate": "2026-04-01"},
        },
        _timeserie_operation("alpha"),
        {
            "type": "set_timeserie_values",
            "scenario_key": "reality",
            "timeserie_key": "alpha",
            "payload": {"values": [{"date": "2026-04-01", "value": 1}]},
        },
    ]

    async def stage() -> tuple[dict[str, Any], dict[str, Any]]:
        async def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            result = await client.call_tool(name, arguments)
            assert isinstance(result.structured_content, dict)
            return result.structured_content

        reset_token = current_principal.set(principal)
        try:
            async with Client(server) as client:
                created = await call(
                    "create_change_set",
                    {"organisation_key": organisation_key, "title": "AI plan"},
                )
                key = created["id"]
                await call(
                    "add_operations", {"change_set_key": key, "operations": operations}
                )
                validated = await call("validate_change_set", {"change_set_key": key})
                submitted = await call("submit_change_set", {"change_set_key": key})
        finally:
            current_principal.reset(reset_token)
        return validated, submitted

    validated, submitted = anyio.run(stage)

    # A dry-run blocked by the tool's own transaction would report
    # statement_timeout, and one after an uncommitted edit would be refused.
    assert validated["ok"] is True
    assert [item["status"] for item in validated["operations"]] == ["ok"] * 3
    assert submitted["ok"] is True
    assert submitted["status"] == "submitted"
    assert submitted["review_url"].endswith(
        f"/schatten/{organisation_key}/metrics?changeSet={submitted['change_set_key']}"
    )
    assert _status(factory, submitted["change_set_key"]) == "submitted"
    assert _count(factory, OrgState, OrgState.name == "Q2") == 0
    assert _count(factory, Timeserie, Timeserie.timeserie_key == "alpha") == 0


def _write_principal(factory: sessionmaker[Session]) -> McpPrincipal:
    """A write grant row, which the change set references, and its principal."""
    now = datetime.now(UTC)
    with factory() as session:
        client = McpOauthClient(
            client_id="client-1",
            client_name="Claude",
            redirect_uris=["http://127.0.0.1:{port}/callback"],
        )
        session.add(client)
        session.flush()
        grant = McpOauthGrant(
            grant_key="grant_creator",
            mcp_oauth_client_id=client.mcp_oauth_client_id,
            user_id=CREATOR_USER_ID,
            scopes=WRITE_SCOPE,
            resource="http://testserver/api/mcp/write",
            created_time=now,
            expires_time=now + timedelta(days=30),
        )
        session.add(grant)
        session.commit()
        return McpPrincipal(
            user_id=CREATOR_USER_ID,
            role="consultant",
            grant_id=grant.grant_id,
            grant_key=grant.grant_key,
            client_id=client.client_id,
            client_name=client.client_name,
            scopes=frozenset({WRITE_SCOPE}),
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
            )
        )
        session.commit()
