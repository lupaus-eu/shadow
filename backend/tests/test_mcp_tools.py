import threading
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any, cast

import anyio
import pytest
from fastmcp import Client, FastMCP
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.mcp_oauth.service import READ_SCOPE
from app.api.v1.mcp_oauth.token_service import McpPrincipal
from app.api.v1.org_states import org_states_service
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
    TypeAttribute,
)
from app.api.v1.organisations.models import Organisation
from app.api.v1.timeserie_generation.generator import GENERATOR_VERSION, generate
from app.api.v1.timeserie_generation.schemas import TimeserieGenerationSpec
from app.api.v1.users.models import User
from app.core.models import Base
from app.mcp import read_server
from app.mcp.auth import current_principal
from app.mcp.read_server import build_read_server
from app.mcp.runtime import McpToolRuntime

USER_ID = 7
PRINCIPAL = McpPrincipal(
    user_id=USER_ID,
    role="consultant",
    grant_id=1,
    grant_key="grant_test",
    client_id="client-test",
    client_name="Claude",
    scopes=frozenset({READ_SCOPE}),
)
DELETED = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    _seed(factory)
    yield factory
    engine.dispose()


def _seed(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        session.add(
            User(
                user_id=USER_ID,
                name="MCP User",
                email="mcp-user@example.test",
                role="consultant",
            )
        )
        beta = Organisation(organisation_key="org_beta", name="Beta")
        alpha = Organisation(organisation_key="org_alpha", name="Alpha")
        deleted = Organisation(
            organisation_key="org_deleted", name="Deleted", deleted_time=DELETED
        )
        session.add_all([beta, alpha, deleted])
        session.flush()
        reality = Scenario(
            organisation_id=beta.organisation_id,
            scenario_key="reality",
            name="Reality",
            description="Current state",
            protected=True,
        )
        session.add_all(
            [
                reality,
                Scenario(
                    organisation_id=beta.organisation_id,
                    scenario_key="growth",
                    name="Growth",
                    protected=False,
                ),
                Scenario(
                    organisation_id=beta.organisation_id,
                    scenario_key="removed",
                    name="Removed",
                    protected=False,
                    deleted_time=DELETED,
                ),
                Scenario(
                    organisation_id=alpha.organisation_id,
                    scenario_key="reality",
                    name="Reality",
                    protected=True,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                OrgState(
                    scenario_id=reality.scenario_id,
                    org_state_key="later",
                    name="Later",
                    target_date=date(2027, 1, 1),
                ),
                OrgState(
                    scenario_id=reality.scenario_id,
                    org_state_key="initial_state",
                    name="Initial state",
                    description="Start",
                    target_date=date(2026, 1, 1),
                ),
                OrgState(
                    scenario_id=reality.scenario_id,
                    org_state_key="gone",
                    name="Gone",
                    target_date=date(2026, 6, 1),
                    deleted_time=DELETED,
                ),
            ]
        )
        _seed_metamodel_and_graph(session, beta, reality)
        _seed_timeseries_and_events(session, reality)
        session.commit()


def _seed_metamodel_and_graph(
    session: Session, organisation: Organisation, scenario: Scenario
) -> None:
    metamodel = Metamodel(organisation_id=organisation.organisation_id, version=1)
    session.add(metamodel)
    session.flush()
    goal_type = NodeType(
        metamodel_id=metamodel.metamodel_id,
        node_type_key="nt_goal",
        name="Goal",
        display_name="Goal",
        ui_color="#D9F99D",
        ui_shape="ellipse",
    )
    metric_type = NodeType(
        metamodel_id=metamodel.metamodel_id,
        node_type_key="nt_metric",
        name="Metric",
        display_name="Metric",
        ui_color="#F4A9BA",
        ui_shape="rectangle",
        timeserie_id="id1",
        timeserie_secondary_id="id2",
        timeserie_id_rule="MEASURED_BY from Goal",
    )
    retired_type = NodeType(
        metamodel_id=metamodel.metamodel_id,
        node_type_key="nt_retired",
        name="Retired",
        display_name="Retired",
        deleted_time=DELETED,
    )
    measured_by = EdgeType(
        metamodel_id=metamodel.metamodel_id,
        edge_type_key="et_measured_by",
        name="Measured by",
        display_name="Measured by",
        ui_style="solid",
        ui_source_end="none",
        ui_target_end="arrow",
    )
    retired_edge_type = EdgeType(
        metamodel_id=metamodel.metamodel_id,
        edge_type_key="et_retired",
        name="Retired",
        display_name="Retired",
        deleted_time=DELETED,
    )
    session.add_all(
        [goal_type, metric_type, retired_type, measured_by, retired_edge_type]
    )
    session.flush()
    session.add_all(
        [
            AllowedConnection(
                metamodel_id=metamodel.metamodel_id,
                edge_type_id=measured_by.edge_type_id,
                source_node_type_id=goal_type.node_type_id,
                target_node_type_id=metric_type.node_type_id,
            ),
            TypeAttribute(
                metamodel_id=metamodel.metamodel_id,
                owner_kind="node_type",
                owner_node_type_id=metric_type.node_type_id,
                attribute_key="a_name",
                name="name",
                display_name="Name",
                data_type="string",
                mandatory=True,
                max_length=100,
                multiline=False,
            ),
            TypeAttribute(
                metamodel_id=metamodel.metamodel_id,
                owner_kind="edge_type",
                owner_edge_type_id=measured_by.edge_type_id,
                attribute_key="a_weight",
                display_name="Weight",
                data_type="float",
                mandatory=False,
            ),
            TypeAttribute(
                metamodel_id=metamodel.metamodel_id,
                owner_kind="node_type",
                owner_node_type_id=retired_type.node_type_id,
                attribute_key="a_retired_owner",
                display_name="Retired owner",
                data_type="string",
            ),
            TypeAttribute(
                metamodel_id=metamodel.metamodel_id,
                owner_kind="edge_type",
                owner_edge_type_id=retired_edge_type.edge_type_id,
                attribute_key="a_retired_edge_owner",
                display_name="Retired edge owner",
                data_type="string",
            ),
            TypeAttribute(
                metamodel_id=metamodel.metamodel_id,
                owner_kind="node_type",
                owner_node_type_id=goal_type.node_type_id,
                attribute_key="a_deleted",
                display_name="Deleted",
                data_type="string",
                deleted_time=DELETED,
            ),
        ]
    )
    revenue = Timeserie(
        scenario_id=scenario.scenario_id,
        timeserie_key="revenue",
        name="Revenue",
        time_unit="month",
        value_unit="number",
    )
    session.add(revenue)
    session.flush()
    goal = GraphNode(
        scenario_id=scenario.scenario_id,
        node_key="goal",
        name="Grow",
        node_type_id=goal_type.node_type_id,
        create_date=date(2026, 1, 1),
        attributes={},
    )
    metric = GraphNode(
        scenario_id=scenario.scenario_id,
        node_key="metric",
        name="Revenue metric",
        description="Monthly revenue",
        node_type_id=metric_type.node_type_id,
        create_date=date(2026, 1, 1),
        position_x=10.0,
        position_y=20.0,
        attributes={"a_name": "Revenue"},
        timeserie_id=revenue.timeserie_id,
    )
    future = GraphNode(
        scenario_id=scenario.scenario_id,
        node_key="future",
        name="Future",
        node_type_id=metric_type.node_type_id,
        create_date=date(2026, 6, 1),
        attributes={},
    )
    ended = GraphNode(
        scenario_id=scenario.scenario_id,
        node_key="ended",
        name="Ended",
        node_type_id=goal_type.node_type_id,
        create_date=date(2025, 1, 1),
        delete_date=date(2025, 12, 31),
        attributes={},
    )
    session.add_all([goal, metric, future, ended])
    session.flush()
    session.add_all(
        [
            GraphEdge(
                scenario_id=scenario.scenario_id,
                edge_key="goal_metric",
                name="Measured by",
                edge_type_id=measured_by.edge_type_id,
                source_graph_node_id=goal.graph_node_id,
                target_graph_node_id=metric.graph_node_id,
                create_date=date(2026, 1, 1),
                attributes={"a_weight": 0.5},
            ),
            GraphEdge(
                scenario_id=scenario.scenario_id,
                edge_key="goal_future",
                name="Measured by",
                edge_type_id=measured_by.edge_type_id,
                source_graph_node_id=goal.graph_node_id,
                target_graph_node_id=future.graph_node_id,
                create_date=date(2026, 1, 1),
                attributes={},
            ),
        ]
    )


def _seed_timeseries_and_events(session: Session, scenario: Scenario) -> None:
    revenue = session.scalars(
        select(Timeserie).where(Timeserie.timeserie_key == "revenue")
    ).one()
    revenue.short_name = "revenue"
    revenue.unit = "EUR"
    visits = Timeserie(
        scenario_id=scenario.scenario_id,
        timeserie_key="visits",
        name="Visits",
        time_unit="day",
        value_unit="number",
    )
    margin = Timeserie(
        scenario_id=scenario.scenario_id,
        timeserie_key="margin",
        name="Margin",
        time_unit="month",
        value_unit="number",
    )
    removed = Timeserie(
        scenario_id=scenario.scenario_id,
        timeserie_key="removed",
        name="Removed",
        time_unit="month",
        value_unit="number",
        deleted_time=DELETED,
    )
    session.add_all([visits, margin, removed])
    session.flush()
    session.add_all(
        [
            *(
                TimeserieValue(
                    timeserie_id=revenue.timeserie_id,
                    date=date(2026, month, 1),
                    value={"value": month * 10},
                )
                for month in range(1, 5)
            ),
            TimeserieValue(
                timeserie_id=revenue.timeserie_id,
                date=date(2026, 5, 1),
                value={"value": 999},
                deleted_time=DELETED,
            ),
            *(
                TimeserieValue(
                    timeserie_id=visits.timeserie_id,
                    date=date(2026, 1, day),
                    value={"value": day},
                )
                for day in range(1, 6)
            ),
            *(
                TimeserieValue(
                    timeserie_id=margin.timeserie_id,
                    date=date(2026, month, 1),
                    value={"value": month * 1.5},
                    is_derived=True,
                )
                for month in range(1, 3)
            ),
            DerivedMetricEquation(
                scenario_id=scenario.scenario_id,
                derived_timeserie_id=margin.timeserie_id,
                formula="revenue * 0.15",
                referenced_timeserie_ids=[revenue.timeserie_id],
            ),
            Event(
                scenario_id=scenario.scenario_id,
                event_key="launch",
                name="Launch",
                target_date=date(2026, 3, 1),
                event_details="Product launch",
            ),
            Event(
                scenario_id=scenario.scenario_id,
                event_key="kickoff",
                name="Kickoff",
                target_date=date(2026, 1, 15),
            ),
            Event(
                scenario_id=scenario.scenario_id,
                event_key="cancelled",
                name="Cancelled",
                target_date=date(2026, 2, 1),
                deleted_time=DELETED,
            ),
        ]
    )


@pytest.fixture()
def runtime(session_factory: sessionmaker[Session]) -> McpToolRuntime:
    return McpToolRuntime(session_factory, anyio.CapacityLimiter(4))


@pytest.fixture()
def server(runtime: McpToolRuntime) -> FastMCP:
    return build_read_server(runtime)


@contextmanager
def _acting_as(principal: McpPrincipal | None) -> Generator[None, None, None]:
    """Stub the principal that `McpBearerAuth` sets for a verified request."""
    reset_token = current_principal.set(principal)
    try:
        yield
    finally:
        current_principal.reset(reset_token)


async def _call(
    server: FastMCP, name: str, arguments: dict[str, object] | None = None
) -> object:
    with _acting_as(PRINCIPAL):
        async with Client(server) as client:
            result = await client.call_tool(name, arguments or {})
    return result.structured_content


async def _call_object(
    server: FastMCP, name: str, arguments: dict[str, object] | None = None
) -> dict[str, Any]:
    result = await _call(server, name, arguments)
    assert isinstance(result, dict)
    return cast(dict[str, Any], result)


async def _error(
    server: FastMCP,
    name: str,
    arguments: dict[str, object] | None = None,
    principal: McpPrincipal | None = PRINCIPAL,
) -> str:
    with _acting_as(principal):
        async with Client(server) as client:
            result = await client.call_tool(name, arguments or {}, raise_on_error=False)
    assert result.is_error
    return "".join(getattr(block, "text", "") for block in result.content)


@pytest.mark.anyio
async def test_read_tools_are_annotated_read_only(server: FastMCP) -> None:
    async with Client(server) as client:
        tools = await client.list_tools()

    assert {tool.name for tool in tools} == {
        "whoami",
        "list_organisations",
        "list_scenarios",
        "list_org_states",
        "get_type_catalog",
        "get_graph",
        "list_timeseries",
        "get_timeserie",
        "list_events",
        "preview_generated_timeserie",
        "list_change_sets",
        "get_change_set",
    }
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False
        assert tool.description


@pytest.mark.anyio
async def test_whoami_returns_the_principals_user(server: FastMCP) -> None:
    assert await _call(server, "whoami") == {
        "id": USER_ID,
        "name": "MCP User",
        "email": "mcp-user@example.test",
        "role": "consultant",
    }


@pytest.mark.anyio
async def test_list_organisations_returns_active_organisations_by_name(
    server: FastMCP,
) -> None:
    assert await _call(server, "list_organisations") == {
        "result": [
            {"id": "org_alpha", "name": "Alpha"},
            {"id": "org_beta", "name": "Beta"},
        ]
    }


@pytest.mark.anyio
async def test_list_scenarios_returns_the_organisations_active_scenarios(
    server: FastMCP,
) -> None:
    result = await _call_object(
        server, "list_scenarios", {"organisation_key": "org_beta"}
    )

    assert result == {
        "result": [
            {"id": "growth", "name": "Growth", "description": "", "protected": False},
            {
                "id": "reality",
                "name": "Reality",
                "description": "Current state",
                "protected": True,
            },
        ]
    }


@pytest.mark.anyio
async def test_list_org_states_returns_active_states_by_target_date(
    server: FastMCP,
) -> None:
    result = await _call_object(
        server,
        "list_org_states",
        {"organisation_key": "org_beta", "scenario_key": "reality"},
    )

    assert result == {
        "result": [
            {
                "id": "initial_state",
                "name": "Initial state",
                "description": "Start",
                "target_date": "2026-01-01",
            },
            {
                "id": "later",
                "name": "Later",
                "description": "",
                "target_date": "2027-01-01",
            },
        ]
    }


@pytest.mark.anyio
async def test_tool_docstrings_state_the_response_limits(server: FastMCP) -> None:
    async with Client(server) as client:
        descriptions = {
            tool.name: tool.description or "" for tool in await client.list_tools()
        }

    assert (
        f"({read_server.LIST_TIMESERIES_MAX_VALUES:,})"
        in (descriptions["list_timeseries"])
    )
    assert (
        f"({read_server.GET_TIMESERIE_MAX_POINTS:,})" in (descriptions["get_timeserie"])
    )
    assert (
        f"first and last {read_server.PREVIEW_SAMPLE_POINTS} points"
        in (descriptions["preview_generated_timeserie"])
    )


@pytest.mark.anyio
async def test_get_type_catalog_returns_types_attributes_and_timeserie_defaults(
    server: FastMCP,
) -> None:
    result = await _call_object(
        server,
        "get_type_catalog",
        {"organisation_key": "org_beta", "scenario_key": "reality"},
    )

    assert result == {
        "node_types": [
            {
                "id": "nt_goal",
                "name": "Goal",
                "display_name": "Goal",
                "color": "#D9F99D",
                "shape": "ellipse",
                "timeserie_id": None,
                "timeserie_secondary_id": None,
                "timeserie_id_rule": None,
            },
            {
                "id": "nt_metric",
                "name": "Metric",
                "display_name": "Metric",
                "color": "#F4A9BA",
                "shape": "rectangle",
                "timeserie_id": "id1",
                "timeserie_secondary_id": "id2",
                "timeserie_id_rule": "MEASURED_BY from Goal",
            },
        ],
        "edge_types": [
            {
                "id": "et_measured_by",
                "name": "Measured by",
                "display_name": "Measured by",
                "style": "solid",
                "source_end": "none",
                "target_end": "arrow",
            }
        ],
        "allowed_connections": [
            {
                "edge_type_id": "et_measured_by",
                "source_node_type_id": "nt_goal",
                "target_node_type_id": "nt_metric",
            }
        ],
        "type_attributes": [
            {
                "owner_kind": "node_type",
                "owner_type_id": "nt_metric",
                "id": "a_name",
                "name": "name",
                "display_name": "Name",
                "data_type": "string",
                "mandatory": True,
                "max_length": 100,
                "multiline": False,
            },
            {
                "owner_kind": "edge_type",
                "owner_type_id": "et_measured_by",
                "id": "a_weight",
                "name": None,
                "display_name": "Weight",
                "data_type": "float",
                "mandatory": False,
                "max_length": None,
                "multiline": None,
            },
        ],
    }


@pytest.mark.anyio
async def test_get_graph_returns_the_graph_visible_at_the_target_date(
    server: FastMCP,
) -> None:
    initial = await _call(
        server,
        "get_graph",
        {
            "organisation_key": "org_beta",
            "scenario_key": "reality",
            "org_state_key": "initial_state",
        },
    )

    assert initial == {
        "id": "reality",
        "name": "Reality",
        "description": "Current state",
        "nodes": [
            {
                "id": "goal",
                "name": "Grow",
                "description": "",
                "node_type_id": "nt_goal",
                "create_date": "2026-01-01",
                "delete_date": None,
                "position": None,
                "attributes": {},
                "timeserie_id": None,
                "timeserie_secondary_id": None,
            },
            {
                "id": "metric",
                "name": "Revenue metric",
                "description": "Monthly revenue",
                "node_type_id": "nt_metric",
                "create_date": "2026-01-01",
                "delete_date": None,
                "position": {"x": 10.0, "y": 20.0},
                "attributes": {"a_name": "Revenue"},
                "timeserie_id": "revenue",
                "timeserie_secondary_id": None,
            },
        ],
        "edges": [
            {
                "id": "goal_metric",
                "name": "Measured by",
                "description": "",
                "edge_type_id": "et_measured_by",
                "source_node_id": "goal",
                "target_node_id": "metric",
                "create_date": "2026-01-01",
                "delete_date": None,
                "attributes": {"a_weight": 0.5},
            }
        ],
    }

    later = await _call_object(
        server,
        "get_graph",
        {
            "organisation_key": "org_beta",
            "scenario_key": "reality",
            "org_state_key": "later",
        },
    )

    assert [node["id"] for node in later["nodes"]] == ["goal", "metric", "future"]
    assert [edge["id"] for edge in later["edges"]] == ["goal_metric", "goal_future"]


@pytest.mark.anyio
async def test_list_timeseries_returns_definitions_without_values_by_default(
    server: FastMCP,
) -> None:
    result = await _call_object(
        server,
        "list_timeseries",
        {"organisation_key": "org_beta", "scenario_key": "reality"},
    )

    assert result == {
        "timeseries": [
            {
                "id": "margin",
                "name": "Margin",
                "short_name": "",
                "description": "",
                "unit": "",
                "time_unit": "month",
                "value_unit": "number",
                "values": [],
                "is_derived": True,
                "derived_formula": "revenue * 0.15",
                "short_name_editable": True,
            },
            {
                "id": "revenue",
                "name": "Revenue",
                "short_name": "revenue",
                "description": "",
                "unit": "EUR",
                "time_unit": "month",
                "value_unit": "number",
                "values": [],
                "is_derived": False,
                "derived_formula": None,
                "short_name_editable": False,
            },
            {
                "id": "visits",
                "name": "Visits",
                "short_name": "",
                "description": "",
                "unit": "",
                "time_unit": "day",
                "value_unit": "number",
                "values": [],
                "is_derived": False,
                "derived_formula": None,
                "short_name_editable": True,
            },
        ],
        "values_included": False,
        "max_values": read_server.LIST_TIMESERIES_MAX_VALUES,
        "truncated": False,
        "truncated_timeserie_ids": [],
    }


@pytest.mark.anyio
async def test_list_timeseries_includes_values_on_request(server: FastMCP) -> None:
    result = await _call_object(
        server,
        "list_timeseries",
        {
            "organisation_key": "org_beta",
            "scenario_key": "reality",
            "include_values": True,
        },
    )

    assert result["values_included"] is True
    assert result["truncated"] is False
    assert {
        timeserie["id"]: [value["value"] for value in timeserie["values"]]
        for timeserie in result["timeseries"]
    } == {
        "margin": [1.5, 3.0],
        "revenue": [10, 20, 30, 40],
        "visits": [1, 2, 3, 4, 5],
    }


@pytest.mark.anyio
async def test_list_timeseries_truncates_values_across_timeseries(
    server: FastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(read_server, "LIST_TIMESERIES_MAX_VALUES", 5)

    result = await _call_object(
        server,
        "list_timeseries",
        {
            "organisation_key": "org_beta",
            "scenario_key": "reality",
            "include_values": True,
        },
    )

    assert result["max_values"] == 5
    assert result["truncated"] is True
    assert result["truncated_timeserie_ids"] == ["revenue", "visits"]
    assert [len(timeserie["values"]) for timeserie in result["timeseries"]] == [
        2,
        3,
        0,
    ]


@pytest.mark.anyio
async def test_get_timeserie_returns_values_within_inclusive_dates(
    server: FastMCP,
) -> None:
    result = await _call_object(
        server,
        "get_timeserie",
        {
            "organisation_key": "org_beta",
            "scenario_key": "reality",
            "timeserie_key": "revenue",
            "from_date": "2026-01-15",
            "to_date": "2026-03-01",
        },
    )

    assert result["timeserie"]["id"] == "revenue"
    assert result["timeserie"]["values"] == [
        {"date": "2026-02-01", "value": 20},
        {"date": "2026-03-01", "value": 30},
    ]
    assert {key: value for key, value in result.items() if key != "timeserie"} == {
        "from_date": "2026-01-15",
        "to_date": "2026-03-01",
        "value_count": 2,
        "max_points": read_server.GET_TIMESERIE_MAX_POINTS,
        "truncated": False,
        "next_from_date": None,
    }


@pytest.mark.anyio
async def test_get_timeserie_leaves_soft_deleted_values_out_of_page_and_count(
    server: FastMCP,
) -> None:
    result = await _call_object(
        server,
        "get_timeserie",
        {
            "organisation_key": "org_beta",
            "scenario_key": "reality",
            "timeserie_key": "revenue",
            "from_date": "2026-01-01",
            "to_date": "2026-12-01",
        },
    )

    assert [value["date"] for value in result["timeserie"]["values"]] == [
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
        "2026-04-01",
    ]
    assert result["value_count"] == 4
    assert result["truncated"] is False


@pytest.mark.anyio
async def test_list_timeseries_without_values_reads_no_values(
    server: FastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("timeserie values were read")

    monkeypatch.setattr(org_states_service, "_active_values_by_timeserie_id", fail)

    result = await _call_object(
        server,
        "list_timeseries",
        {"organisation_key": "org_beta", "scenario_key": "reality"},
    )

    assert [timeserie["id"] for timeserie in result["timeseries"]] == [
        "margin",
        "revenue",
        "visits",
    ]


@pytest.mark.anyio
async def test_get_timeserie_reads_one_page_of_values_within_the_dates(
    server: FastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(read_server, "GET_TIMESERIE_MAX_POINTS", 2)
    read = org_states_service._active_timeserie_values  # pyright: ignore[reportPrivateUsage]
    read_dates: list[list[date]] = []

    def spy(*args: Any, **kwargs: Any) -> list[TimeserieValue]:
        values = read(*args, **kwargs)
        read_dates.append([value.date for value in values])
        return values

    monkeypatch.setattr(org_states_service, "_active_timeserie_values", spy)

    result = await _call_object(
        server,
        "get_timeserie",
        {
            "organisation_key": "org_beta",
            "scenario_key": "reality",
            "timeserie_key": "visits",
            "from_date": "2026-01-02",
            "to_date": "2026-01-05",
        },
    )

    assert read_dates == [[date(2026, 1, day) for day in (2, 3, 4)]]
    assert result["value_count"] == 4
    assert result["truncated"] is True
    assert result["next_from_date"] == "2026-01-04"


@pytest.mark.anyio
async def test_get_timeserie_truncates_and_points_to_the_next_page(
    server: FastMCP, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(read_server, "GET_TIMESERIE_MAX_POINTS", 3)
    arguments: dict[str, object] = {
        "organisation_key": "org_beta",
        "scenario_key": "reality",
        "timeserie_key": "visits",
    }

    first = await _call_object(server, "get_timeserie", arguments)

    assert [value["date"] for value in first["timeserie"]["values"]] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]
    assert first["value_count"] == 5
    assert first["truncated"] is True
    assert first["next_from_date"] == "2026-01-04"

    second = await _call_object(
        server, "get_timeserie", {**arguments, "from_date": first["next_from_date"]}
    )

    assert [value["value"] for value in second["timeserie"]["values"]] == [4, 5]
    assert second["truncated"] is False
    assert second["next_from_date"] is None


@pytest.mark.anyio
async def test_get_timeserie_rejects_reversed_dates(server: FastMCP) -> None:
    error = await _error(
        server,
        "get_timeserie",
        {
            "organisation_key": "org_beta",
            "scenario_key": "reality",
            "timeserie_key": "revenue",
            "from_date": "2026-03-01",
            "to_date": "2026-02-01",
        },
    )

    assert error == "from_date must not be after to_date."


@pytest.mark.anyio
async def test_list_events_returns_active_events_by_target_date(
    server: FastMCP,
) -> None:
    result = await _call_object(
        server,
        "list_events",
        {"organisation_key": "org_beta", "scenario_key": "reality"},
    )

    assert result == {
        "result": [
            {
                "id": "kickoff",
                "name": "Kickoff",
                "target_date": "2026-01-15",
                "event_details": "",
            },
            {
                "id": "launch",
                "name": "Launch",
                "target_date": "2026-03-01",
                "event_details": "Product launch",
            },
        ]
    }


PREVIEW_SPEC: dict[str, object] = {
    "startDate": "2026-01-01",
    "periods": 24,
    "timeUnit": "month",
    "baseLevel": 100,
    "trend": {"type": "linear", "slope": 2},
    "noise": {"std": 3},
    "seed": 42,
}


@pytest.mark.anyio
async def test_preview_generated_timeserie_summarises_the_generated_values(
    server: FastMCP,
) -> None:
    spec = TimeserieGenerationSpec.model_validate(PREVIEW_SPEC)
    points = generate(spec)
    values = [point.value for point in points]

    result = await _call_object(
        server, "preview_generated_timeserie", {"spec": PREVIEW_SPEC}
    )

    assert result["generator_version"] == GENERATOR_VERSION
    assert result["point_count"] == 24
    assert result["first_date"] == "2026-01-01"
    assert result["last_date"] == "2027-12-01"
    assert result["min"] == min(values)
    assert result["max"] == max(values)
    assert result["mean"] == pytest.approx(sum(values) / len(values))
    assert result["first_points"] == [
        {"date": point.date.isoformat(), "value": point.value} for point in points[:5]
    ]
    assert result["last_points"] == [
        {"date": point.date.isoformat(), "value": point.value} for point in points[-5:]
    ]


@pytest.mark.anyio
async def test_preview_generated_timeserie_is_deterministic_per_seed(
    server: FastMCP,
) -> None:
    first = await _call_object(
        server, "preview_generated_timeserie", {"spec": PREVIEW_SPEC}
    )
    again = await _call(server, "preview_generated_timeserie", {"spec": PREVIEW_SPEC})
    reseeded = await _call(
        server, "preview_generated_timeserie", {"spec": {**PREVIEW_SPEC, "seed": 7}}
    )

    assert first == again
    assert first != reseeded


@pytest.mark.anyio
async def test_preview_generated_timeserie_persists_nothing(
    server: FastMCP, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        before = session.query(TimeserieValue).count()

    await _call(server, "preview_generated_timeserie", {"spec": PREVIEW_SPEC})

    with session_factory() as session:
        assert session.query(TimeserieValue).count() == before


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"startDate": "2026-01-15"}, "is not a valid month start date"),
        ({"endDate": "2026-12-01"}, "periods"),
        ({"periods": "12"}, "periods"),
        ({"unknown": 1}, "unknown"),
    ],
)
async def test_preview_generated_timeserie_rejects_an_invalid_spec(
    server: FastMCP, changes: dict[str, object], expected: str
) -> None:
    error = await _error(
        server, "preview_generated_timeserie", {"spec": {**PREVIEW_SPEC, **changes}}
    )

    assert expected in error


@pytest.mark.anyio
async def test_preview_generated_timeserie_reports_non_finite_values(
    server: FastMCP,
) -> None:
    spec = {
        **PREVIEW_SPEC,
        "baseLevel": 1e300,
        "trend": {"type": "percent", "percentPerPeriod": 1000},
        "noise": None,
    }

    error = await _error(server, "preview_generated_timeserie", {"spec": spec})

    assert error.startswith("The spec generates values that are not finite numbers")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        (
            "list_scenarios",
            {"organisation_key": "org_deleted"},
            "Organisation not found.",
        ),
        (
            "get_type_catalog",
            {"organisation_key": "org_beta", "scenario_key": "removed"},
            "Scenario not found.",
        ),
        (
            "get_graph",
            {
                "organisation_key": "org_beta",
                "scenario_key": "reality",
                "org_state_key": "gone",
            },
            "Organisation state not found.",
        ),
        (
            "list_timeseries",
            {"organisation_key": "org_missing", "scenario_key": "reality"},
            "Organisation not found.",
        ),
        (
            "get_timeserie",
            {
                "organisation_key": "org_beta",
                "scenario_key": "reality",
                "timeserie_key": "removed",
            },
            "Timeserie not found.",
        ),
        (
            "list_events",
            {"organisation_key": "org_beta", "scenario_key": "growth_missing"},
            "Scenario not found.",
        ),
        (
            "list_org_states",
            {"organisation_key": "org_missing", "scenario_key": "reality"},
            "Organisation not found.",
        ),
        (
            "list_org_states",
            {"organisation_key": "org_beta", "scenario_key": "removed"},
            "Scenario not found.",
        ),
    ],
)
async def test_unknown_keys_are_tool_errors_with_the_service_message(
    server: FastMCP, name: str, arguments: dict[str, object], message: str
) -> None:
    assert await _error(server, name, arguments) == message


@pytest.mark.anyio
@pytest.mark.parametrize("organisation_key", ["", "o" * 129, 5])
async def test_key_arguments_are_validated(
    server: FastMCP, organisation_key: object
) -> None:
    error = await _error(
        server, "list_scenarios", {"organisation_key": organisation_key}
    )

    assert "organisation_key" in error


@pytest.mark.anyio
async def test_tools_fail_without_a_verified_principal(server: FastMCP) -> None:
    assert (
        await _error(server, "list_organisations", principal=None)
        == "Authentication required"
    )


@pytest.mark.anyio
async def test_tool_work_runs_in_a_worker_thread_under_the_shared_limiter(
    runtime: McpToolRuntime,
) -> None:
    event_loop_thread = threading.current_thread()

    def work(session: Session, principal: McpPrincipal) -> tuple[bool, float, int]:
        return (
            threading.current_thread() is not event_loop_thread,
            runtime.limiter.borrowed_tokens,
            principal.user_id,
        )

    with _acting_as(PRINCIPAL):
        assert await runtime.run(work) == (True, 1, USER_ID)
    assert runtime.limiter.borrowed_tokens == 0
