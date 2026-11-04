import hashlib
import io
import logging
import os
import secrets
import subprocess
import sys
from collections.abc import Callable, Generator, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx2
import pytest
from auth_helpers import authenticate_test_client
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, event, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.api.v1.mcp_oauth.token_service as token_service
import app.api.v1.org_states.org_states_service as org_states_service
from app.api.v1.ai_change_sets.models import AiChangeSet
from app.api.v1.auth.rate_limit import FixedWindowRateLimiter
from app.api.v1.mcp_oauth.models import McpOauthClient, McpOauthGrant, McpOauthToken
from app.api.v1.mcp_oauth.service import READ_SCOPE, WRITE_SCOPE
from app.api.v1.organisations.models import Organisation
from app.api.v1.users.models import User
from app.core.config import Settings
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app

ORIGIN = "http://testserver"
MCP_PATH = "/api/mcp"
RESOURCE = f"{ORIGIN}{MCP_PATH}"
RESOURCE_METADATA = f"{ORIGIN}/.well-known/oauth-protected-resource{MCP_PATH}"
BOTH_SCOPES = f"{READ_SCOPE} {WRITE_SCOPE}"
# The endpoints that TASK-074 replaced with `/api/mcp`.
LEGACY_PATHS = ("/api/mcp/read", "/api/mcp/write")
READ_TOOL_NAMES = (
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
    "get_change_set_review",
)
WRITE_TOOL_NAMES = (
    "create_change_set",
    "add_operations",
    "remove_operation",
    "validate_change_set",
    "submit_change_set",
    "discard_change_set",
)
REVIEW_TOOL_NAMES = ("apply_change_set", "reject_change_set")
PROMPT_NAMES = ("model_building", "timeseries_generation")
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
USER_ID = 7
OTHER_USER_ID = 8
LOGGER_NAMES = ("", "fastmcp")
BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _seeded_session_factory(engine: Engine) -> sessionmaker[Session]:
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with factory() as session:
        session.add(
            User(
                user_id=USER_ID,
                name="MCP User",
                email="mcp-user@example.test",
                role="consultant",
            )
        )
        session.commit()
    return factory


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine: Engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield _seeded_session_factory(engine)
    engine.dispose()


@contextmanager
def _client(
    session_factory: sessionmaker[Session], **overrides: object
) -> Generator[TestClient, None, None]:
    settings = Settings.model_validate({"MCP_ENABLED": True, **overrides})
    app = create_app(settings=settings, mcp_session_factory=session_factory)

    def override_get_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    # The context manager runs the lifespan that starts the MCP server.
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    with _client(session_factory) as test_client:
        yield test_client


def _issue_token(
    session_factory: sessionmaker[Session],
    *,
    scopes: str = BOTH_SCOPES,
    resource: str = RESOURCE,
    user_id: int = USER_ID,
) -> tuple[str, str]:
    """Store an active grant and access token; return (token, grant_key)."""
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    grant_key = f"grant_{uuid4().hex}"
    with session_factory() as session:
        client = McpOauthClient(
            client_id=secrets.token_urlsafe(32),
            client_name="Claude",
            redirect_uris=["http://127.0.0.1:{port}/callback"],
        )
        session.add(client)
        session.flush()
        grant = McpOauthGrant(
            grant_key=grant_key,
            mcp_oauth_client_id=client.mcp_oauth_client_id,
            user_id=user_id,
            scopes=scopes,
            resource=resource,
            created_time=now,
            expires_time=now + timedelta(days=30),
        )
        session.add(grant)
        session.flush()
        session.add(
            McpOauthToken(
                token_hash=hashlib.sha256(token.encode()).digest(),
                grant_id=grant.grant_id,
                kind="access",
                created_time=now,
                expires_time=now + timedelta(hours=1),
            )
        )
        session.commit()
    return token, grant_key


def _rpc(
    client: TestClient,
    method: str,
    params: dict[str, object] | None = None,
    *,
    token: str | None = None,
    path: str = MCP_PATH,
) -> httpx2.Response:
    headers = dict(MCP_HEADERS)
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        path,
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


def _whoami(client: TestClient, token: str) -> httpx2.Response:
    return _rpc(client, "tools/call", {"name": "whoami", "arguments": {}}, token=token)


def _tool_names(client: TestClient, token: str) -> set[str]:
    response = _rpc(client, "tools/list", token=token)
    assert response.status_code == 200, response.text
    return {tool["name"] for tool in response.json()["result"]["tools"]}


def _prompt_names(client: TestClient, token: str) -> set[str]:
    response = _rpc(client, "prompts/list", token=token)
    assert response.status_code == 200, response.text
    return {prompt["name"] for prompt in response.json()["result"]["prompts"]}


def _assert_invalid_token(response: httpx2.Response) -> None:
    assert response.status_code == 401, response.text
    assert response.headers["www-authenticate"] == (
        f'Bearer error="invalid_token", resource_metadata="{RESOURCE_METADATA}"'
    )
    assert response.json()["error"] == "invalid_token"


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_missing_token_gets_401_with_resource_metadata(
    client: TestClient, method: str
) -> None:
    response = client.request(method, MCP_PATH, headers=MCP_HEADERS)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        f'Bearer resource_metadata="{RESOURCE_METADATA}"'
    )
    assert response.headers["cache-control"] == "no-store"


def test_other_authorization_scheme_counts_as_no_token(client: TestClient) -> None:
    response = client.post(
        MCP_PATH, headers={**MCP_HEADERS, "Authorization": "Basic dXNlcg=="}
    )

    assert response.status_code == 401
    assert "error=" not in response.headers["www-authenticate"]


def test_browser_session_cookie_is_not_accepted(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    authenticate_test_client(client, session_factory, user_id=1)

    response = _rpc(client, "tools/list")

    assert response.status_code == 401
    assert "error=" not in response.headers["www-authenticate"]


def test_mcp_token_is_not_accepted_on_api_v1(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    token, _ = _issue_token(session_factory)

    response = client.get(
        "/api/v1/organisations", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "authorization",
    [
        ["Bearer not-a-token"],
        [f"Bearer {secrets.token_urlsafe(32)}"],
        ["Bearer "],
        [f"Bearer {secrets.token_urlsafe(32)}", f"Bearer {secrets.token_urlsafe(32)}"],
    ],
    ids=["malformed", "unknown", "empty", "repeated-header"],
)
def test_presented_but_rejected_token_gets_invalid_token(
    client: TestClient, authorization: list[str]
) -> None:
    response = client.post(
        MCP_PATH,
        headers=[
            *MCP_HEADERS.items(),
            *(("Authorization", value) for value in authorization),
        ],
    )

    _assert_invalid_token(response)


def test_valid_token_reaches_the_server(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    token, _ = _issue_token(session_factory)

    whoami = _whoami(client, token)

    assert whoami.status_code == 200, whoami.text
    assert whoami.headers["cache-control"] == "no-store"
    assert whoami.json()["result"]["structuredContent"] == {
        "id": USER_ID,
        "name": "MCP User",
        "email": "mcp-user@example.test",
        "role": "consultant",
    }


def test_one_server_lists_read_and_write_tools_and_prompts(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    token, _ = _issue_token(session_factory)

    initialize = _rpc(
        client,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
        token=token,
    )
    tools = _tool_names(client, token)

    assert initialize.status_code == 200, initialize.text
    assert initialize.json()["result"]["serverInfo"]["name"] == "Schatten"
    assert len(READ_TOOL_NAMES) == 13
    assert len(WRITE_TOOL_NAMES) == 6
    assert tools == {*READ_TOOL_NAMES, *WRITE_TOOL_NAMES}
    assert _prompt_names(client, token) == set(PROMPT_NAMES)


def test_the_review_switch_adds_apply_and_reject(
    session_factory: sessionmaker[Session],
) -> None:
    token, _ = _issue_token(session_factory)

    with _client(session_factory, MCP_CHANGE_SET_REVIEW_ENABLED=True) as client:
        tools = _tool_names(client, token)

    assert len(tools) == 21
    assert tools == {*READ_TOOL_NAMES, *WRITE_TOOL_NAMES, *REVIEW_TOOL_NAMES}


def _create_change_set(client: TestClient, token: str) -> httpx2.Response:
    return _rpc(
        client,
        "tools/call",
        {
            "name": "create_change_set",
            "arguments": {"organisation_key": "org_acme", "title": "AI plan"},
        },
        token=token,
    )


def _seed_organisation(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(Organisation(organisation_key="org_acme", name="Acme"))
        session.commit()


def test_token_stages_a_change_set_for_its_grant(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    _seed_organisation(session_factory)
    token, grant_key = _issue_token(session_factory)

    response = _create_change_set(client, token)

    assert response.status_code == 200, response.text
    assert response.json()["result"]["structuredContent"]["status"] == "draft"
    with session_factory() as session:
        change_set = session.scalars(select(AiChangeSet)).one()
        grant = session.scalars(
            select(McpOauthGrant).where(McpOauthGrant.grant_key == grant_key)
        ).one()
        oauth_client = session.get_one(McpOauthClient, grant.mcp_oauth_client_id)
        assert change_set.grant_id == grant.grant_id
        assert change_set.client_id == oauth_client.client_id
        assert change_set.client_name == "Claude"
        assert change_set.created_by == USER_ID


def _stub_role_scopes(
    monkeypatch: pytest.MonkeyPatch, role: str, scopes: frozenset[str]
) -> None:
    monkeypatch.setitem(token_service.ROLE_SCOPES, role, scopes)


def test_read_only_role_sees_only_read_tools_and_prompts(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_role_scopes(monkeypatch, "consultant", frozenset({READ_SCOPE}))
    token, _ = _issue_token(session_factory)

    with _client(session_factory, MCP_CHANGE_SET_REVIEW_ENABLED=True) as client:
        tools = _tool_names(client, token)
        prompts = _prompt_names(client, token)
        whoami = _whoami(client, token)

    assert tools == set(READ_TOOL_NAMES)
    assert prompts == set(PROMPT_NAMES)
    assert whoami.status_code == 200, whoami.text


def test_read_only_grant_sees_only_read_tools(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    # A client that asked for `scope=schatten.read` holds a read-only grant.
    token, _ = _issue_token(session_factory, scopes=READ_SCOPE)

    assert _tool_names(client, token) == set(READ_TOOL_NAMES)


@pytest.mark.parametrize("tool", [*WRITE_TOOL_NAMES, *REVIEW_TOOL_NAMES])
def test_read_only_grant_gets_unknown_tool_for_write_tools(
    session_factory: sessionmaker[Session], tool: str
) -> None:
    _seed_organisation(session_factory)
    token, _ = _issue_token(session_factory, scopes=READ_SCOPE)
    arguments = {"organisation_key": "org_acme", "title": "AI plan"}

    with _client(session_factory, MCP_CHANGE_SET_REVIEW_ENABLED=True) as client:
        response = _rpc(
            client, "tools/call", {"name": tool, "arguments": arguments}, token=token
        )

    assert response.status_code == 200, response.text
    assert f"Unknown tool: '{tool}'" in response.text
    with session_factory() as session:
        assert session.scalars(select(AiChangeSet)).all() == []


@pytest.mark.parametrize("tool", [*WRITE_TOOL_NAMES, *REVIEW_TOOL_NAMES])
def test_read_only_role_gets_unknown_tool_for_write_tools(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
) -> None:
    _seed_organisation(session_factory)
    _stub_role_scopes(monkeypatch, "consultant", frozenset({READ_SCOPE}))
    token, _ = _issue_token(session_factory)
    arguments = {"organisation_key": "org_acme", "title": "AI plan"}

    with _client(session_factory, MCP_CHANGE_SET_REVIEW_ENABLED=True) as client:
        response = _rpc(
            client, "tools/call", {"name": tool, "arguments": arguments}, token=token
        )

    assert response.status_code == 200, response.text
    assert f"Unknown tool: '{tool}'" in response.text
    with session_factory() as session:
        assert session.scalars(select(AiChangeSet)).all() == []


def test_role_change_shows_or_hides_write_tools_on_the_next_call(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_role_scopes(monkeypatch, "consultant", frozenset({READ_SCOPE}))
    token, _ = _issue_token(session_factory)

    def set_role(role: str) -> None:
        with session_factory() as session:
            session.execute(
                update(User).where(User.user_id == USER_ID).values(role=role)
            )
            session.commit()

    read_only = _tool_names(client, token)
    set_role("admin")
    read_write = _tool_names(client, token)
    set_role("consultant")
    read_only_again = _tool_names(client, token)

    assert read_only == read_only_again == set(READ_TOOL_NAMES)
    assert read_write == {*READ_TOOL_NAMES, *WRITE_TOOL_NAMES}


def test_concurrent_calls_act_as_each_tokens_own_user(tmp_path: Path) -> None:
    # A file database: the in-memory one shares a single connection, which
    # concurrent requests cannot use.
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'mcp.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = _seeded_session_factory(engine)
    with factory() as session:
        session.add(
            User(
                user_id=OTHER_USER_ID,
                name="Other User",
                email="other-user@example.test",
                role="admin",
            )
        )
        session.commit()
    tokens = {
        USER_ID: _issue_token(factory)[0],
        OTHER_USER_ID: _issue_token(factory, user_id=OTHER_USER_ID)[0],
    }

    with _client(factory) as client:
        # Sequential first calls write each grant's last_used_time, so the
        # concurrent calls below change no row.
        warm_up = {user_id: _whoami(client, token) for user_id, token in tokens.items()}
        calls = [user_id for _ in range(20) for user_id in tokens]

        def call(user_id: int) -> httpx2.Response:
            return _whoami(client, tokens[user_id])

        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(call, calls))
    engine.dispose()

    for user_id, response in [*warm_up.items(), *zip(calls, responses, strict=True)]:
        assert response.status_code == 200, response.text
        assert response.json()["result"]["structuredContent"]["id"] == user_id


@pytest.mark.parametrize(
    "resource", ["https://other.example/api/mcp", "http://testserver:8000/api/mcp"]
)
def test_token_for_another_origins_resource_gets_invalid_token(
    client: TestClient, session_factory: sessionmaker[Session], resource: str
) -> None:
    token, _ = _issue_token(session_factory, resource=resource)

    response = _rpc(client, "tools/list", token=token)

    _assert_invalid_token(response)


def test_missing_read_scope_gets_403_insufficient_scope(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_role_scopes(monkeypatch, "consultant", frozenset({WRITE_SCOPE}))
    token, _ = _issue_token(session_factory)

    response = _create_change_set(client, token)

    assert response.status_code == 403
    assert response.headers["www-authenticate"] == (
        'Bearer error="insufficient_scope", scope="schatten.read", '
        f'resource_metadata="{RESOURCE_METADATA}"'
    )
    assert response.json()["error"] == "insufficient_scope"


def test_role_change_takes_effect_on_the_next_call(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_role_scopes(monkeypatch, "consultant", frozenset({WRITE_SCOPE}))
    token, _ = _issue_token(session_factory)

    def set_role(role: str) -> None:
        with session_factory() as session:
            session.execute(
                update(User).where(User.user_id == USER_ID).values(role=role)
            )
            session.commit()

    set_role("admin")
    allowed = _whoami(client, token)
    set_role("consultant")
    denied = _whoami(client, token)

    assert allowed.status_code == 200
    assert allowed.json()["result"]["structuredContent"]["role"] == "admin"
    assert denied.status_code == 403


def _expire_token(session: Session, grant_key: str) -> None:
    session.execute(
        update(McpOauthToken)
        .where(McpOauthToken.grant_id == _grant_id(session, grant_key))
        .values(
            created_time=datetime.now(UTC) - timedelta(hours=2),
            expires_time=datetime.now(UTC) - timedelta(seconds=1),
        )
    )


def _revoke_token(session: Session, grant_key: str) -> None:
    session.execute(
        update(McpOauthToken)
        .where(McpOauthToken.grant_id == _grant_id(session, grant_key))
        .values(revoked_time=datetime.now(UTC))
    )


def _revoke_grant(session: Session, grant_key: str) -> None:
    session.execute(
        update(McpOauthGrant)
        .where(McpOauthGrant.grant_key == grant_key)
        .values(revoked_time=datetime.now(UTC))
    )


def _expire_grant(session: Session, grant_key: str) -> None:
    session.execute(
        update(McpOauthGrant)
        .where(McpOauthGrant.grant_key == grant_key)
        .values(
            created_time=datetime.now(UTC) - timedelta(days=31),
            expires_time=datetime.now(UTC) - timedelta(seconds=1),
        )
    )


def _delete_user(session: Session, _grant_key: str) -> None:
    session.execute(
        update(User)
        .where(User.user_id == USER_ID)
        .values(deleted_time=datetime.now(UTC))
    )


def _grant_id(session: Session, grant_key: str) -> int:
    return session.scalars(
        select(McpOauthGrant.grant_id).where(McpOauthGrant.grant_key == grant_key)
    ).one()


@pytest.mark.parametrize(
    "invalidate",
    [_expire_token, _revoke_token, _revoke_grant, _expire_grant, _delete_user],
    ids=[
        "expired-token",
        "revoked-token",
        "revoked-grant",
        "expired-grant",
        "deleted-user",
    ],
)
def test_invalidated_access_stops_on_the_next_call(
    client: TestClient,
    session_factory: sessionmaker[Session],
    invalidate: Callable[[Session, str], None],
) -> None:
    token, grant_key = _issue_token(session_factory)
    assert _whoami(client, token).status_code == 200

    with session_factory() as session:
        invalidate(session, grant_key)
        session.commit()

    _assert_invalid_token(_whoami(client, token))


def test_rate_limit_is_per_grant_for_reads_and_writes_on_mcp_rate_limiter_only(
    session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with _client(session_factory, MCP_RATE_LIMIT_PER_MINUTE=2) as client:
        app = cast(FastAPI, client.app)
        mcp_limiter = cast(FixedWindowRateLimiter, app.state.mcp_rate_limiter)
        calls: list[tuple[str, str, int]] = []
        allow = mcp_limiter.allow

        def recording_allow(bucket: str, address: str, limit: int) -> bool:
            calls.append((bucket, address, limit))
            return allow(bucket, address, limit)

        def forbidden_allow(*_args: object, **_kwargs: object) -> bool:
            raise AssertionError("MCP requests must not use this limiter")

        monkeypatch.setattr(mcp_limiter, "allow", recording_allow)
        monkeypatch.setattr(app.state.auth_rate_limiter, "allow", forbidden_allow)
        monkeypatch.setattr(app.state.oauth_rate_limiter, "allow", forbidden_allow)
        token, grant_key = _issue_token(session_factory)
        other_token, other_grant_key = _issue_token(session_factory)

        # One grant covers reads and writes, so they share its bucket.
        statuses = [
            _whoami(client, token).status_code,
            _create_change_set(client, token).status_code,
            _whoami(client, token).status_code,
        ]
        other = _whoami(client, other_token)

    assert statuses == [200, 200, 429]
    assert other.status_code == 200
    assert calls == [
        ("mcp", grant_key, 2),
        ("mcp", grant_key, 2),
        ("mcp", grant_key, 2),
        ("mcp", other_grant_key, 2),
    ]


@pytest.mark.parametrize("path", [MCP_PATH, *LEGACY_PATHS])
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_mcp_disabled_registers_no_mcp_routes(
    session_factory: sessionmaker[Session], path: str, method: str
) -> None:
    token, _ = _issue_token(session_factory)
    app = create_app(settings=Settings(), mcp_session_factory=session_factory)

    with TestClient(app) as client:
        response = client.request(
            method,
            path,
            headers={**MCP_HEADERS, "Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404


@pytest.mark.parametrize("with_token", [True, False])
@pytest.mark.parametrize("path", LEGACY_PATHS)
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_legacy_read_and_write_endpoints_are_gone(
    client: TestClient,
    session_factory: sessionmaker[Session],
    path: str,
    method: str,
    with_token: bool,
) -> None:
    headers = dict(MCP_HEADERS)
    if with_token:
        token, _ = _issue_token(session_factory)
        headers["Authorization"] = f"Bearer {token}"

    response = client.request(method, path, headers=headers)

    assert response.status_code == 404
    assert "www-authenticate" not in response.headers


def test_fastmcp_is_imported_only_when_mcp_is_enabled() -> None:
    # A fresh interpreter, because this test process has already imported it.
    script = """
import sys

import app.main
from app.core.config import Settings

assert "fastmcp" not in sys.modules, "fastmcp imported with MCP disabled"
app.main.create_app(settings=Settings.model_validate({"MCP_ENABLED": True}))
assert "fastmcp" in sys.modules, "fastmcp not imported with MCP enabled"
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        cwd=BACKEND_DIRECTORY,
        env={**os.environ, "APP_ENV": "test", "MCP_ENABLED": "false"},
    )

    assert completed.returncode == 0, completed.stderr


def test_authenticated_get_and_delete_are_not_supported_statelessly(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    token, _ = _issue_token(session_factory)
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {token}"}

    assert client.get(MCP_PATH, headers=headers).status_code == 405
    assert client.delete(MCP_PATH, headers=headers).status_code == 405
    assert client.put(MCP_PATH, headers=headers).status_code == 405


@pytest.mark.parametrize("with_token", [True, False])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_trailing_slash_is_not_redirected(
    client: TestClient,
    session_factory: sessionmaker[Session],
    method: str,
    with_token: bool,
) -> None:
    headers = dict(MCP_HEADERS)
    if with_token:
        token, _ = _issue_token(session_factory)
        headers["Authorization"] = f"Bearer {token}"

    response = client.request(
        method, f"{MCP_PATH}/", headers=headers, follow_redirects=False
    )

    assert response.status_code == 404
    assert "location" not in response.headers
    assert response.headers["cache-control"] == "no-store"


@contextmanager
def _captured_logs() -> Generator[io.StringIO, None, None]:
    """Capture what the root and the non-propagating fastmcp loggers emit."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    loggers = [logging.getLogger(name) for name in LOGGER_NAMES]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield stream
    finally:
        for logger in loggers:
            logger.removeHandler(handler)


def test_tokens_and_tool_arguments_are_never_logged(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, _ = _issue_token(session_factory)
    rejected_token = secrets.token_urlsafe(32)
    argument = f"org_{uuid4().hex}"

    def failing_list(_session: Session, organisation_key: str) -> list[object]:
        raise RuntimeError(f"database error for {organisation_key}")

    with _captured_logs() as logs:
        _rpc(client, "tools/list", token=rejected_token)
        not_found = _rpc(
            client,
            "tools/call",
            {"name": "list_scenarios", "arguments": {"organisation_key": argument}},
            token=token,
        )
        monkeypatch.setattr(
            org_states_service, "list_organisation_scenarios", failing_list
        )
        failed = _rpc(
            client,
            "tools/call",
            {"name": "list_scenarios", "arguments": {"organisation_key": argument}},
            token=token,
        )

    assert not_found.json()["result"]["isError"] is True
    assert failed.json()["result"]["content"][0]["text"] == "Internal error"
    output = logs.getvalue()
    assert "RuntimeError" in output
    for secret in (token, rejected_token, argument):
        assert secret not in output
