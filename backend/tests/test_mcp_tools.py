import threading
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime

import anyio
import pytest
from fastmcp import Client, FastMCP
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.mcp_oauth.service import READ_SCOPE
from app.api.v1.mcp_oauth.token_service import McpPrincipal
from app.api.v1.org_states.models import OrgState, Scenario
from app.api.v1.organisations.models import Organisation
from app.api.v1.users.models import User
from app.core.models import Base
from app.mcp.auth import current_principal
from app.mcp.read_server import build_read_server
from app.mcp.runtime import McpToolRuntime
from app.mcp.write_server import build_write_server

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
        session.commit()


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
    result = await _call(server, "list_scenarios", {"organisation_key": "org_beta"})

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
    result = await _call(
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
@pytest.mark.parametrize(
    ("name", "arguments", "message"),
    [
        (
            "list_scenarios",
            {"organisation_key": "org_deleted"},
            "Organisation not found.",
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


@pytest.mark.anyio
async def test_write_server_is_a_scaffold_without_tools() -> None:
    async with Client(build_write_server()) as client:
        assert await client.list_tools() == []
