import os

os.environ["APP_ENV"] = "test"
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any

import anyio
import psycopg
import pytest
from fastmcp import Client, FastMCP
from sqlalchemy import StaticPool, create_engine, func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.ai_change_sets.engine as engine
from app.api.v1.ai_change_sets.models import AiChangeSet, AiChangeSetOperation
from app.api.v1.mcp_oauth.service import WRITE_SCOPE
from app.api.v1.mcp_oauth.token_service import McpPrincipal
from app.api.v1.org_states.models import (
    DerivedMetricEquation,
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
)
from app.api.v1.organisations import service as organisations_service
from app.api.v1.organisations.models import Organisation
from app.api.v1.organisations.schemas import OrganisationCreateRequest
from app.api.v1.timeserie_generation.generator import GENERATOR_VERSION
from app.api.v1.users.models import User
from app.core.config import Settings
from app.core.models import Base
from app.mcp import read_server, write_server
from app.mcp.auth import current_principal
from app.mcp.read_server import build_read_server
from app.mcp.runtime import McpToolRuntime
from app.mcp.write_server import build_write_server

CREATOR_USER_ID = 7
OTHER_USER_ID = 8
PUBLIC_ORIGIN = "https://schatten.example.test"
SETTINGS = Settings.model_validate(
    {"MCP_ENABLED": True, "PUBLIC_ORIGIN": PUBLIC_ORIGIN}
)
CREATOR = McpPrincipal(
    user_id=CREATOR_USER_ID,
    role="consultant",
    grant_id=11,
    grant_key="grant_creator",
    client_id="client-creator",
    client_name="Claude",
    scopes=frozenset({WRITE_SCOPE}),
)
OTHER_USER = McpPrincipal(
    user_id=OTHER_USER_ID,
    role="admin",
    grant_id=12,
    grant_key="grant_other",
    client_id="client-other",
    client_name="Other client",
    scopes=frozenset({WRITE_SCOPE}),
)
# Another grant of the creating User, for example a second MCP client.
CREATOR_SECOND_GRANT = McpPrincipal(
    user_id=CREATOR_USER_ID,
    role="consultant",
    grant_id=13,
    grant_key="grant_creator_second",
    client_id="client-creator-second",
    client_name="Claude Code",
    scopes=frozenset({WRITE_SCOPE}),
)
WRITE_TOOLS = {
    "create_change_set",
    "add_operations",
    "remove_operation",
    "validate_change_set",
    "submit_change_set",
    "discard_change_set",
}
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
STRUCTURE_OPERATIONS: list[dict[str, Any]] = [
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
]
TIMESERIE_OPERATIONS: list[dict[str, Any]] = [
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
        "type": "create_event",
        "ref": "$reorg",
        "scenario_key": "$plan",
        "payload": {"name": "Reorganisation", "targetDate": "2026-03-01"},
    },
]
EVENT_OPERATION: dict[str, Any] = {
    "type": "create_event",
    "scenario_key": "reality",
    "payload": {"name": "Launch", "targetDate": "2026-01-01"},
}


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    sqlite: Engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(sqlite)
    factory = sessionmaker(bind=sqlite, autocommit=False, autoflush=False)
    _seed_users_and_default_metamodel(factory)
    yield factory
    sqlite.dispose()


@pytest.fixture()
def organisation_key(session_factory: sessionmaker[Session]) -> str:
    with session_factory() as session:
        return organisations_service.create_organisation(
            session, OrganisationCreateRequest(name="Acme Corp"), CREATOR_USER_ID
        ).id


@pytest.fixture()
def runtime(session_factory: sessionmaker[Session]) -> McpToolRuntime:
    return McpToolRuntime(session_factory, anyio.CapacityLimiter(4))


@pytest.fixture()
def server(runtime: McpToolRuntime) -> FastMCP:
    return build_write_server(runtime, SETTINGS)


@pytest.fixture()
def reader(runtime: McpToolRuntime) -> FastMCP:
    return build_read_server(runtime)


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
                    user_id=OTHER_USER_ID,
                    name="Other",
                    email="other@example.test",
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


@contextmanager
def _acting_as(principal: McpPrincipal | None) -> Generator[None, None, None]:
    """Stub the principal that `McpBearerAuth` sets for a verified request."""
    reset_token = current_principal.set(principal)
    try:
        yield
    finally:
        current_principal.reset(reset_token)


async def _call(
    server: FastMCP,
    name: str,
    arguments: dict[str, object] | None = None,
    principal: McpPrincipal = CREATOR,
) -> dict[str, Any]:
    with _acting_as(principal):
        async with Client(server) as client:
            result = await client.call_tool(name, arguments or {})
    assert isinstance(result.structured_content, dict)
    return result.structured_content


async def _error(
    server: FastMCP,
    name: str,
    arguments: dict[str, object] | None = None,
    principal: McpPrincipal = CREATOR,
) -> str:
    with _acting_as(principal):
        async with Client(server) as client:
            result = await client.call_tool(name, arguments or {}, raise_on_error=False)
    assert result.is_error
    return "".join(getattr(block, "text", "") for block in result.content)


async def _create(server: FastMCP, organisation_key: str) -> str:
    created = await _call(
        server,
        "create_change_set",
        {
            "organisation_key": organisation_key,
            "title": "AI plan",
            "rationale": "Generated with the user.",
        },
    )
    return created["id"]


async def _create_with(
    server: FastMCP, organisation_key: str, operations: list[dict[str, Any]]
) -> str:
    change_set_key = await _create(server, organisation_key)
    await _call(
        server,
        "add_operations",
        {"change_set_key": change_set_key, "operations": operations},
    )
    return change_set_key


def _row_counts(factory: sessionmaker[Session]) -> dict[str, int]:
    with factory() as session:
        return {
            model.__tablename__: session.scalar(select(func.count()).select_from(model))
            or 0
            for model in BUSINESS_MODELS
        }


def _statuses(result: dict[str, Any]) -> list[str]:
    return [item["status"] for item in result["operations"]]


@pytest.mark.anyio
async def test_write_tools_stage_only_and_none_applies(server: FastMCP) -> None:
    async with Client(server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    assert set(tools) == WRITE_TOOLS
    assert not [name for name in tools if "apply" in name or "reject" in name]
    for name, tool in tools.items():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is False
        assert tool.annotations.open_world_hint is False
        assert tool.annotations.destructive_hint is (
            name in {"remove_operation", "discard_change_set"}
        )
        assert tool.annotations.idempotent_hint is (name == "validate_change_set")


@pytest.mark.anyio
async def test_write_instructions_and_docstrings_explain_the_workflow(
    server: FastMCP,
) -> None:
    async with Client(server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    instructions = server.instructions or ""
    assert "create_change_set, add_operations, validate_change_set" in instructions
    assert "Nothing is applied until a\nperson approves it" in instructions
    add = tools["add_operations"].description or ""
    assert "`$ref`" in add
    assert "referred to verbatim" in add
    assert "stops at the first failing operation" in (
        tools["validate_change_set"].description or ""
    )
    for tool in tools.values():
        if tool.name not in {"remove_operation", "discard_change_set"}:
            assert "Nothing is applied until a human approves it" in " ".join(
                (tool.description or "").split()
            )


@pytest.mark.anyio
async def test_full_staging_workflow_changes_no_business_table(
    server: FastMCP,
    reader: FastMCP,
    session_factory: sessionmaker[Session],
    organisation_key: str,
) -> None:
    before = _row_counts(session_factory)

    created = await _call(
        server,
        "create_change_set",
        {
            "organisation_key": organisation_key,
            "title": " AI plan ",
            "rationale": "Generated with the user.",
        },
    )
    change_set_key = created["id"]
    first = await _call(
        server,
        "add_operations",
        {"change_set_key": change_set_key, "operations": STRUCTURE_OPERATIONS},
    )
    second = await _call(
        server,
        "add_operations",
        {"change_set_key": change_set_key, "operations": TIMESERIE_OPERATIONS},
    )
    validated = await _call(
        server, "validate_change_set", {"change_set_key": change_set_key}
    )
    submitted = await _call(
        server, "submit_change_set", {"change_set_key": change_set_key}
    )
    detail = await _call(reader, "get_change_set", {"change_set_key": change_set_key})

    assert created["status"] == "draft"
    assert created["title"] == "AI plan"
    assert created["organisation_key"] == organisation_key
    assert created["operation_count"] == 0
    assert created["created_by"] == CREATOR_USER_ID
    assert created["client_id"] == "client-creator"
    assert created["client_name"] == "Claude"
    assert first["added_positions"] == [0, 1, 2, 3, 4]
    assert second["added_positions"] == [5, 6, 7]
    assert second["change_set"]["operation_count"] == 8
    # The change set creates a scenario, so it has no scenario reference.
    assert second["change_set"]["scenario_key"] is None
    assert validated["ok"] is True
    assert _statuses(validated) == ["ok"] * 8
    assert set(validated["refs"]) == {"$plan", "$start", "$reorg"}
    assert validated["replacements"]["operations"][0]["replaces_existing"] is False
    assert submitted == {
        "change_set_key": change_set_key,
        "status": "submitted",
        "ok": True,
        "operations": submitted["operations"],
        "review_url": f"{PUBLIC_ORIGIN}/schatten/{organisation_key}/metrics"
        f"?changeSet={change_set_key}",
    }
    assert _statuses(submitted) == ["ok"] * 8
    assert detail["status"] == "submitted"
    assert detail["operations"][6]["operation"] == {
        "type": "generate_timeserie_values",
        **{
            key: value
            for key, value in TIMESERIE_OPERATIONS[1].items()
            if key != "type"
        },
        "spec": detail["operations"][6]["operation"]["spec"],
    }
    assert detail["operations"][6]["frozen_values"] == {
        "generator_version": GENERATOR_VERSION,
        "value_count": 12,
        "first_date": "2026-01-01",
        "last_date": "2026-12-01",
    }
    assert detail["operations"][0]["ref"] == "$plan"
    assert detail["validation_result"]["ok"] is True
    assert detail["applied_result"] is None
    with session_factory() as session:
        change_set = session.scalars(select(AiChangeSet)).one()
        assert change_set.grant_id == CREATOR.grant_id
        assert change_set.client_id == CREATOR.client_id
        assert change_set.client_name == CREATOR.client_name
        assert change_set.created_by == CREATOR_USER_ID
        assert change_set.modified_by == CREATOR_USER_ID
    assert _row_counts(session_factory) == before


@pytest.mark.anyio
async def test_validation_returns_each_operation_and_stops_at_the_first_error(
    server: FastMCP,
    reader: FastMCP,
    organisation_key: str,
) -> None:
    operations: list[dict[str, Any]] = [
        EVENT_OPERATION,
        {
            "type": "create_node",
            "scenario_key": "reality",
            "org_state_key": "initial_state",
            "payload": {"id": "ghost", "name": "Ghost", "nodeTypeId": "nt_missing"},
        },
        {**EVENT_OPERATION, "payload": {"name": "Later", "targetDate": "2026-02-01"}},
    ]
    change_set_key = await _create_with(server, organisation_key, operations)

    failed = await _call(
        server, "validate_change_set", {"change_set_key": change_set_key}
    )
    stored = await _call(reader, "get_change_set", {"change_set_key": change_set_key})
    not_submitted = await _call(
        server, "submit_change_set", {"change_set_key": change_set_key}
    )
    await _call(
        server, "remove_operation", {"change_set_key": change_set_key, "position": 1}
    )
    fixed = await _call(
        server, "validate_change_set", {"change_set_key": change_set_key}
    )

    assert failed["ok"] is False
    assert _statuses(failed) == ["ok", "error", "not_run"]
    error = failed["operations"][1]["error"]
    assert error["code"] == "domain_error"
    assert failed["operations"][2]["error"] is None
    assert [item["error"] for item in stored["operations"]] == [None, error, None]
    assert stored["validation_result"] == {
        "ok": False,
        "operations": failed["operations"],
        "refs": {},
    }
    # The stored result never contains the informational replacement flags.
    assert "replacements" not in stored["validation_result"]
    assert not_submitted["status"] == "draft"
    assert not_submitted["review_url"] is None
    assert _statuses(not_submitted) == ["ok", "error", "not_run"]
    assert fixed["ok"] is True
    assert [item["position"] for item in fixed["operations"]] == [0, 2]


@pytest.mark.anyio
async def test_validation_reports_replacements_for_information_only(
    server: FastMCP,
    reader: FastMCP,
    session_factory: sessionmaker[Session],
    organisation_key: str,
) -> None:
    with session_factory() as session:
        reality = session.scalars(select(Scenario)).one()
        timeserie = Timeserie(
            scenario_id=reality.scenario_id,
            timeserie_key="sales",
            name="Sales",
            short_name="sales",
            time_unit="month",
            value_unit="number",
        )
        session.add(timeserie)
        session.flush()
        session.add(
            TimeserieValue(
                timeserie_id=timeserie.timeserie_id,
                date=date(2026, 1, 1),
                value={"value": 5},
            )
        )
        session.commit()
    change_set_key = await _create_with(
        server,
        organisation_key,
        [
            {
                "type": "set_timeserie_values",
                "scenario_key": "reality",
                "timeserie_key": "sales",
                "payload": {"values": [{"date": "2026-02-01", "value": 6}]},
            }
        ],
    )

    validated = await _call(
        server, "validate_change_set", {"change_set_key": change_set_key}
    )
    detail = await _call(reader, "get_change_set", {"change_set_key": change_set_key})

    assert validated["ok"] is True
    replacement = validated["replacements"]["operations"][0]
    assert replacement["replaces_existing"] is True
    assert replacement["summary"]["timeserie_key"] == "sales"
    assert replacement["summary"]["value_count"] == 1
    assert detail["scenario_key"] == "reality"
    assert "replacements" not in detail["validation_result"]


@pytest.mark.anyio
async def test_editing_a_submitted_change_set_is_rejected(
    server: FastMCP, organisation_key: str
) -> None:
    change_set_key = await _create_with(server, organisation_key, [EVENT_OPERATION])
    await _call(server, "submit_change_set", {"change_set_key": change_set_key})
    message = (
        "Only a draft change set can be changed or validated; this one is submitted."
    )

    for name, arguments in _edit_calls(change_set_key):
        assert await _error(server, name, arguments) == message, name


@pytest.mark.anyio
async def test_editing_another_users_change_set_is_rejected(
    server: FastMCP,
    reader: FastMCP,
    session_factory: sessionmaker[Session],
    organisation_key: str,
) -> None:
    change_set_key = await _create_with(server, organisation_key, [EVENT_OPERATION])
    message = (
        "Only the User who created this change set can change it; other Users "
        "can only read it."
    )

    for name, arguments in _edit_calls(change_set_key):
        assert await _error(server, name, arguments, OTHER_USER) == message, name
    readable = await _call(
        reader, "get_change_set", {"change_set_key": change_set_key}, OTHER_USER
    )
    # Another grant of the creating User may change the draft.
    added = await _call(
        server,
        "add_operations",
        {"change_set_key": change_set_key, "operations": [EVENT_OPERATION]},
        CREATOR_SECOND_GRANT,
    )

    assert readable["status"] == "draft"
    assert readable["operation_count"] == 1
    assert added["added_positions"] == [1]
    with session_factory() as session:
        change_set = session.scalars(select(AiChangeSet)).one()
        assert change_set.status == "draft"
        # The staging grant and client stay those that created the draft.
        assert change_set.grant_id == CREATOR.grant_id
        assert change_set.client_id == CREATOR.client_id


def _edit_calls(change_set_key: str) -> list[tuple[str, dict[str, object]]]:
    key: dict[str, object] = {"change_set_key": change_set_key}
    return [
        ("add_operations", {**key, "operations": [EVENT_OPERATION]}),
        ("remove_operation", {**key, "position": 0}),
        ("validate_change_set", key),
        ("submit_change_set", key),
        ("discard_change_set", key),
    ]


@pytest.mark.anyio
async def test_discard_ends_the_draft(
    server: FastMCP, reader: FastMCP, organisation_key: str
) -> None:
    change_set_key = await _create_with(server, organisation_key, [EVENT_OPERATION])

    discarded = await _call(
        server, "discard_change_set", {"change_set_key": change_set_key}
    )
    error = await _error(
        server,
        "add_operations",
        {"change_set_key": change_set_key, "operations": [EVENT_OPERATION]},
    )
    detail = await _call(reader, "get_change_set", {"change_set_key": change_set_key})

    assert discarded["status"] == "discarded"
    assert error == (
        "Only a draft change set can be changed or validated; this one is discarded."
    )
    assert detail["status"] == "discarded"
    assert detail["operation_count"] == 1


@pytest.mark.anyio
async def test_operation_limits_are_enforced(
    server: FastMCP, organisation_key: str
) -> None:
    change_set_key = await _create(server, organisation_key)
    key: dict[str, object] = {"change_set_key": change_set_key}

    too_many_in_one_call = await _error(
        server, "add_operations", {**key, "operations": [EVENT_OPERATION] * 501}
    )
    await _call(
        server, "add_operations", {**key, "operations": [EVENT_OPERATION] * 500}
    )
    too_many_in_total = await _error(
        server, "add_operations", {**key, "operations": [EVENT_OPERATION]}
    )

    assert "operations" in too_many_in_one_call
    assert "500" in too_many_in_one_call
    assert too_many_in_total == (
        "A change set has at most 500 operations; this one would have 501."
    )


@pytest.mark.anyio
async def test_value_limits_are_enforced(
    server: FastMCP, organisation_key: str
) -> None:
    daily = {
        "type": "generate_timeserie_values",
        "scenario_key": "reality",
        "timeserie_key": "daily",
        "spec": {
            "startDate": "2026-01-01",
            "periods": 10_001,
            "timeUnit": "day",
            "baseLevel": 1,
            "seed": 1,
        },
    }
    change_set_key = await _create(server, organisation_key)

    error = await _error(
        server,
        "add_operations",
        {"change_set_key": change_set_key, "operations": [daily, daily]},
    )

    assert error == (
        "A change set sets or generates at most 20000 timeserie values; this one "
        "would have 20002."
    )


@pytest.mark.anyio
async def test_tool_boundary_input_limits(
    server: FastMCP,
    session_factory: sessionmaker[Session],
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_title = await _error(
        server,
        "create_change_set",
        {"organisation_key": organisation_key, "title": "t" * 201},
    )
    long_rationale = await _error(
        server,
        "create_change_set",
        {"organisation_key": organisation_key, "title": "t", "rationale": "r" * 4001},
    )
    nul_title = await _error(
        server,
        "create_change_set",
        {"organisation_key": organisation_key, "title": "AI\x00plan"},
    )
    change_set_key = await _create(server, organisation_key)
    nul_payload = await _error(
        server,
        "add_operations",
        {
            "change_set_key": change_set_key,
            "operations": [
                {
                    **EVENT_OPERATION,
                    "payload": {"name": "A\x00", "targetDate": "2026-01-01"},
                }
            ],
        },
    )
    monkeypatch.setattr(write_server, "MAX_ADD_OPERATIONS_BYTES", 100)
    too_large = await _error(
        server,
        "add_operations",
        {"change_set_key": change_set_key, "operations": [EVENT_OPERATION] * 2},
    )

    assert "title" in long_title
    assert "rationale" in long_rationale
    assert nul_title == "Text must not contain NUL characters."
    assert nul_payload == "Text must not contain NUL characters."
    assert too_large.startswith(
        "One add_operations call stores at most 100 bytes of operation JSON"
    )
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AiChangeSet)) == 1
        assert (
            session.scalar(select(func.count()).select_from(AiChangeSetOperation)) == 0
        )


@pytest.mark.anyio
async def test_unknown_change_set_and_organisation_are_errors(
    server: FastMCP,
    reader: FastMCP,
    session_factory: sessionmaker[Session],
    organisation_key: str,
) -> None:
    change_set_key = await _create(server, organisation_key)
    with session_factory() as session:
        session.execute(
            update(Organisation).values(deleted_time=datetime(2026, 1, 1, tzinfo=UTC))
        )
        session.commit()

    assert (
        await _error(
            server,
            "create_change_set",
            {"organisation_key": "org_missing", "title": "AI plan"},
        )
        == "Organisation not found."
    )
    for name, arguments in _edit_calls(change_set_key):
        assert await _error(server, name, arguments) == "Change set not found.", name
    assert (
        await _error(reader, "get_change_set", {"change_set_key": change_set_key})
        == "Change set not found."
    )


@pytest.mark.anyio
async def test_remove_operation_errors(server: FastMCP, organisation_key: str) -> None:
    change_set_key = await _create_with(
        server, organisation_key, STRUCTURE_OPERATIONS[:2]
    )

    missing = await _error(
        server, "remove_operation", {"change_set_key": change_set_key, "position": 9}
    )
    referenced = await _error(
        server, "remove_operation", {"change_set_key": change_set_key, "position": 0}
    )

    assert missing == "Operation not found."
    assert referenced.startswith("Operation 0 cannot be removed.")


@pytest.mark.anyio
async def test_every_write_tool_sets_the_statement_timeout(
    server: FastMCP, organisation_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    original = engine.set_statement_timeout

    def spy(session: Session, settings: Settings) -> None:
        calls.append(settings.ai_change_set_statement_timeout_ms)
        original(session, settings)

    monkeypatch.setattr(engine, "set_statement_timeout", spy)
    change_set_key = await _create(server, organisation_key)
    for name, arguments in [
        ("add_operations", {"operations": [EVENT_OPERATION, EVENT_OPERATION]}),
        ("remove_operation", {"position": 1}),
        ("validate_change_set", {}),
        ("discard_change_set", {}),
    ]:
        calls.append(-1)
        await _call(server, name, {"change_set_key": change_set_key, **arguments})

    timeout = SETTINGS.ai_change_set_statement_timeout_ms
    # The tool's own transaction, then validation's dry-run and replacement reads.
    assert calls == [
        timeout,
        -1,
        timeout,
        -1,
        timeout,
        -1,
        timeout,
        timeout,
        timeout,
        -1,
        timeout,
    ]


def _query_cancelled() -> OperationalError:
    return OperationalError(
        "SELECT 1",
        {},
        psycopg.errors.QueryCanceled("canceling statement due to statement timeout"),
    )


@pytest.mark.anyio
async def test_a_database_timeout_is_a_retryable_tool_error(
    server: FastMCP, organisation_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    change_set_key = await _create(server, organisation_key)

    def timed_out(*_args: object, **_kwargs: object) -> object:
        raise _query_cancelled()

    monkeypatch.setattr(engine, "add_operations", timed_out)

    assert await _error(
        server,
        "add_operations",
        {"change_set_key": change_set_key, "operations": [EVENT_OPERATION]},
    ) == ("The change set is busy or the database timed out; try again shortly.")


@pytest.mark.anyio
async def test_read_tools_list_and_filter_change_sets(
    server: FastMCP,
    reader: FastMCP,
    organisation_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    on_reality = await _create_with(server, organisation_key, [EVENT_OPERATION])
    new_scenario = await _create_with(
        server, organisation_key, STRUCTURE_OPERATIONS[:1]
    )
    empty = await _create(server, organisation_key)
    await _call(server, "submit_change_set", {"change_set_key": on_reality})
    await _call(server, "discard_change_set", {"change_set_key": empty})

    def keys(result: dict[str, Any]) -> list[str]:
        return [item["id"] for item in result["change_sets"]]

    every = await _call(
        reader, "list_change_sets", {"organisation_key": organisation_key}
    )
    submitted = await _call(
        reader,
        "list_change_sets",
        {"organisation_key": organisation_key, "status": "submitted"},
    )
    by_scenario = await _call(
        reader,
        "list_change_sets",
        {"organisation_key": organisation_key, "scenario_key": "reality"},
        OTHER_USER,
    )
    unknown_scenario = await _error(
        reader,
        "list_change_sets",
        {"organisation_key": organisation_key, "scenario_key": "missing"},
    )
    unknown_status = await _error(
        reader,
        "list_change_sets",
        {"organisation_key": organisation_key, "status": "pending"},
    )
    monkeypatch.setattr(read_server, "LIST_CHANGE_SETS_MAX_ITEMS", 2)
    bounded = await _call(
        reader, "list_change_sets", {"organisation_key": organisation_key}
    )

    assert set(keys(every)) == {on_reality, new_scenario, empty}
    assert every["truncated"] is False
    assert every["max_items"] == 100
    summary = next(item for item in every["change_sets"] if item["id"] == on_reality)
    assert summary["scenario_key"] == "reality"
    assert summary["operation_count"] == 1
    assert "operations" not in summary
    assert keys(submitted) == [on_reality]
    assert keys(by_scenario) == [on_reality]
    assert unknown_scenario == "Scenario not found."
    assert "status" in unknown_status
    assert len(keys(bounded)) == 2
    assert bounded["truncated"] is True
    assert bounded["max_items"] == 2


@pytest.mark.anyio
async def test_change_set_read_tools_are_read_only(reader: FastMCP) -> None:
    async with Client(reader) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    for name in ("list_change_sets", "get_change_set"):
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
