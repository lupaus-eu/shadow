import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import CheckConstraint, StaticPool, Table, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.mcp_oauth.models import (
    McpOauthAuthorizationRequest,
    McpOauthClient,
    McpOauthGrant,
    McpOauthToken,
)
from app.api.v1.users.models import User
from app.core.models import Base

# Migration 020 (TASK-074): one MCP resource carries read, or read and write.
MCP_RESOURCE = "https://app.localhost/api/mcp"
READ_SCOPES = "shadow.read"
READ_WRITE_SCOPES = "shadow.read shadow.write"
CODE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def _enable_sqlite_foreign_keys(
    dbapi_connection: sqlite3.Connection, _: object
) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


@pytest.fixture()
def session() -> Iterator[Session]:
    engine: Engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _user(session: Session) -> User:
    user = User(name="MCP User", email="mcp@example.local", role="consultant")
    session.add(user)
    session.commit()
    return user


def _client(session: Session, client_id: str = "client-1") -> McpOauthClient:
    client = McpOauthClient(
        client_id=client_id,
        client_name="Claude",
        redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
        created_time=NOW,
        created_ip="203.0.113.10",
    )
    session.add(client)
    session.commit()
    return client


def _grant(
    session: Session,
    *,
    grant_key: str = "grant-1",
    scopes: str = READ_WRITE_SCOPES,
    resource: str = MCP_RESOURCE,
    expires_time: datetime | None = NOW + timedelta(days=30),
) -> McpOauthGrant:
    user = session.query(User).first() or _user(session)
    client = session.query(McpOauthClient).first() or _client(session)
    grant = McpOauthGrant(
        grant_key=grant_key,
        mcp_oauth_client_id=client.mcp_oauth_client_id,
        user_id=user.user_id,
        scopes=scopes,
        resource=resource,
        created_time=NOW,
        expires_time=expires_time,
    )
    session.add(grant)
    return grant


def _token(grant_id: int, token_hash: bytes, kind: str = "access") -> McpOauthToken:
    return McpOauthToken(
        token_hash=token_hash,
        grant_id=grant_id,
        kind=kind,
        created_time=NOW,
        expires_time=NOW + timedelta(hours=1),
    )


def _authorization_request(
    client_id: int,
    request_id_hash: bytes,
    *,
    scopes: str = READ_WRITE_SCOPES,
    resource: str = MCP_RESOURCE,
) -> McpOauthAuthorizationRequest:
    return McpOauthAuthorizationRequest(
        request_id_hash=request_id_hash,
        mcp_oauth_client_id=client_id,
        redirect_uri="https://claude.ai/api/mcp/auth_callback",
        state="client-state",
        code_challenge=CODE_CHALLENGE,
        scopes=scopes,
        resource=resource,
        created_time=NOW,
        expires_time=NOW + timedelta(minutes=10),
    )


def _assert_rejected(session: Session) -> None:
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_valid_grant_with_tokens_and_redeemed_request_is_stored(
    session: Session,
) -> None:
    grant = _grant(session)
    session.commit()
    session.add(_token(grant.grant_id, b"a" * 32))
    refresh = _token(grant.grant_id, b"r" * 32, kind="refresh")
    refresh.replaced_by_hash = b"n" * 32
    session.add(refresh)
    request = _authorization_request(grant.mcp_oauth_client_id, b"q" * 32)
    request.user_id = grant.user_id
    request.code_hash = b"c" * 32
    request.code_expires_time = NOW + timedelta(seconds=60)
    request.consumed_time = NOW + timedelta(seconds=5)
    request.grant_id = grant.grant_id
    session.add(request)
    session.commit()

    assert session.query(McpOauthToken).count() == 2
    assert request.grant_id == grant.grant_id


def test_tables_store_only_hashes_of_secrets() -> None:
    plaintext = {
        "token",
        "access_token",
        "refresh_token",
        "code",
        "authorization_code",
        "request_id",
        "client_secret",
    }
    for model in (
        McpOauthClient,
        McpOauthAuthorizationRequest,
        McpOauthGrant,
        McpOauthToken,
    ):
        assert not plaintext & set(cast(Table, model.__table__).columns.keys())

    request_table = cast(Table, McpOauthAuthorizationRequest.__table__)
    token_table = cast(Table, McpOauthToken.__table__)
    assert [column.name for column in request_table.primary_key] == ["request_id_hash"]
    assert [column.name for column in token_table.primary_key] == ["token_hash"]
    assert "code_hash" in request_table.columns
    assert "replaced_by_hash" in token_table.columns


@pytest.mark.parametrize(
    "column",
    ["token_hash", "replaced_by_hash"],
)
def test_token_hash_columns_reject_non_sha256_lengths(
    session: Session, column: str
) -> None:
    grant = _grant(session)
    session.commit()
    token = _token(grant.grant_id, b"t" * 32, kind="refresh")
    setattr(token, column, b"short")
    session.add(token)

    _assert_rejected(session)


@pytest.mark.parametrize("column", ["request_id_hash", "code_hash"])
def test_authorization_request_hash_columns_reject_non_sha256_lengths(
    session: Session, column: str
) -> None:
    user = _user(session)
    client = _client(session)
    request = _authorization_request(client.mcp_oauth_client_id, b"q" * 32)
    request.user_id = user.user_id
    request.code_expires_time = NOW + timedelta(seconds=60)
    request.code_hash = b"c" * 32
    setattr(request, column, b"short")
    session.add(request)

    _assert_rejected(session)


def test_token_kind_check_allows_only_access_and_refresh(session: Session) -> None:
    grant = _grant(session)
    session.commit()
    session.add(_token(grant.grant_id, b"i" * 32, kind="id"))

    _assert_rejected(session)


def test_only_refresh_tokens_have_a_replacement(session: Session) -> None:
    grant = _grant(session)
    session.commit()
    token = _token(grant.grant_id, b"a" * 32, kind="access")
    token.replaced_by_hash = b"n" * 32
    session.add(token)

    _assert_rejected(session)


def _add_grant_row(session: Session, scopes: str, resource: str) -> None:
    _grant(session, scopes=scopes, resource=resource)


def _add_authorization_request_row(
    session: Session, scopes: str, resource: str
) -> None:
    client = _client(session)
    session.add(
        _authorization_request(
            client.mcp_oauth_client_id, b"q" * 32, scopes=scopes, resource=resource
        )
    )


ScopedRowBuilder = Callable[[Session, str, str], None]
scoped_rows = pytest.mark.parametrize(
    "add_row",
    [_add_grant_row, _add_authorization_request_row],
    ids=["grant", "authorization_request"],
)


@scoped_rows
@pytest.mark.parametrize("scopes", [READ_SCOPES, READ_WRITE_SCOPES])
def test_scoped_rows_accept_read_or_read_and_write_on_the_mcp_resource(
    session: Session, add_row: ScopedRowBuilder, scopes: str
) -> None:
    add_row(session, scopes, MCP_RESOURCE)
    session.commit()

    stored = {
        (grant.scopes, grant.resource) for grant in session.query(McpOauthGrant)
    } | {
        (request.scopes, request.resource)
        for request in session.query(McpOauthAuthorizationRequest)
    }
    assert stored == {(scopes, MCP_RESOURCE)}


@scoped_rows
@pytest.mark.parametrize(
    "scopes",
    [
        "shadow.write",
        "shadow.write shadow.read",
        "shadow.admin",
        "shadow.read shadow.admin",
        "shadow.read shadow.write shadow.admin",
        "shadow.read  shadow.write",
        "shadow.read shadow.read",
        "",
    ],
)
def test_scoped_rows_reject_any_other_scopes(
    session: Session, add_row: ScopedRowBuilder, scopes: str
) -> None:
    add_row(session, scopes, MCP_RESOURCE)

    _assert_rejected(session)


@scoped_rows
@pytest.mark.parametrize(
    "resource",
    [
        "https://app.localhost/api/mcp/read",
        "https://app.localhost/api/mcp/write",
        "https://app.localhost/api/mcp/",
        "https://app.localhost/api/mcpx",
    ],
)
@pytest.mark.parametrize("scopes", [READ_SCOPES, READ_WRITE_SCOPES])
def test_scoped_rows_reject_any_other_resource(
    session: Session, add_row: ScopedRowBuilder, scopes: str, resource: str
) -> None:
    add_row(session, scopes, resource)

    _assert_rejected(session)


def test_scope_and_resource_checks_mirror_migration_020() -> None:
    expected = {
        McpOauthGrant: {
            "ck_mcp_oauth_grants_scope": (
                "scopes IN ('shadow.read', 'shadow.read shadow.write')"
            ),
            "ck_mcp_oauth_grants_resource": "resource LIKE '%/api/mcp'",
        },
        McpOauthAuthorizationRequest: {
            "ck_mcp_oauth_authorization_requests_scope": (
                "scopes IN ('shadow.read', 'shadow.read shadow.write')"
            ),
            "ck_mcp_oauth_authorization_requests_resource": (
                "resource LIKE '%/api/mcp'"
            ),
        },
    }
    for model, checks in expected.items():
        table = cast(Table, model.__table__)
        constraints = {
            constraint.name: str(constraint.sqltext)
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
            and isinstance(constraint.name, str)
            and ("scope" in constraint.name or "resource" in constraint.name)
        }
        assert constraints == checks


def test_grant_expiry_is_required(session: Session) -> None:
    _grant(session, expires_time=None)

    _assert_rejected(session)


def test_grant_expiry_must_follow_creation(session: Session) -> None:
    _grant(session, expires_time=NOW)

    _assert_rejected(session)


def test_grant_revoker_requires_revocation_time(session: Session) -> None:
    grant = _grant(session)
    grant.revoked_by = grant.user_id

    _assert_rejected(session)


def test_client_id_is_unique(session: Session) -> None:
    _client(session, "same-client")
    session.add(
        McpOauthClient(
            client_id="same-client",
            client_name="Other",
            redirect_uris=["http://127.0.0.1:3000/callback"],
        )
    )

    _assert_rejected(session)


def test_grant_key_is_unique(session: Session) -> None:
    _grant(session, grant_key="same-grant")
    session.commit()
    _grant(session, grant_key="same-grant")

    _assert_rejected(session)


def test_token_hash_is_unique(session: Session) -> None:
    grant = _grant(session)
    session.commit()
    grant_id = grant.grant_id
    session.add(_token(grant_id, b"t" * 32))
    session.commit()
    session.expunge_all()
    session.add(_token(grant_id, b"t" * 32, kind="refresh"))

    _assert_rejected(session)


def test_authorization_code_hash_is_unique(session: Session) -> None:
    user = _user(session)
    client = _client(session)
    for request_id_hash in (b"1" * 32, b"2" * 32):
        request = _authorization_request(client.mcp_oauth_client_id, request_id_hash)
        request.user_id = user.user_id
        request.code_hash = b"c" * 32
        request.code_expires_time = NOW + timedelta(seconds=60)
        session.add(request)

    _assert_rejected(session)


@pytest.mark.parametrize("client_name", ["", "x" * 101])
def test_client_name_length_is_bounded(session: Session, client_name: str) -> None:
    session.add(
        McpOauthClient(
            client_id="client-1",
            client_name=client_name,
            redirect_uris=["http://127.0.0.1:3000/callback"],
        )
    )

    _assert_rejected(session)


@pytest.mark.parametrize(
    "redirect_uris",
    [[], [f"http://127.0.0.1:{port}/callback" for port in range(11)], {"a": 1}],
)
def test_redirect_uris_are_a_bounded_array(
    session: Session, redirect_uris: object
) -> None:
    session.add(
        McpOauthClient(
            client_id="client-1",
            client_name="Claude Code",
            redirect_uris=redirect_uris,
        )
    )

    _assert_rejected(session)


def test_code_requires_expiry_and_deciding_user(session: Session) -> None:
    client = _client(session)
    request = _authorization_request(client.mcp_oauth_client_id, b"q" * 32)
    request.code_hash = b"c" * 32
    request.code_expires_time = NOW + timedelta(seconds=60)
    session.add(request)

    _assert_rejected(session)


def test_redeemed_grant_requires_consumed_code(session: Session) -> None:
    grant = _grant(session)
    session.commit()
    request = _authorization_request(grant.mcp_oauth_client_id, b"q" * 32)
    request.user_id = grant.user_id
    request.code_hash = b"c" * 32
    request.code_expires_time = NOW + timedelta(seconds=60)
    request.grant_id = grant.grant_id
    session.add(request)

    _assert_rejected(session)


def test_code_challenge_must_be_an_s256_challenge(session: Session) -> None:
    client = _client(session)
    request = _authorization_request(client.mcp_oauth_client_id, b"q" * 32)
    request.code_challenge = "plain-verifier"
    session.add(request)

    _assert_rejected(session)


def _blank_client_id(session: Session) -> None:
    session.add(
        McpOauthClient(
            client_id=" \t",
            client_name="Claude",
            redirect_uris=["http://127.0.0.1:3000/callback"],
        )
    )


def _blank_created_ip(session: Session) -> None:
    session.add(
        McpOauthClient(
            client_id="client-1",
            client_name="Claude",
            redirect_uris=["http://127.0.0.1:3000/callback"],
            created_ip=" ",
        )
    )


def _blank_grant_key(session: Session) -> None:
    _grant(session, grant_key=" ")


def _token_expiry_not_after_creation(session: Session) -> None:
    grant = _grant(session)
    session.commit()
    token = _token(grant.grant_id, b"t" * 32)
    token.expires_time = NOW
    session.add(token)


def _request(session: Session) -> McpOauthAuthorizationRequest:
    user = _user(session)
    client = _client(session)
    request = _authorization_request(client.mcp_oauth_client_id, b"q" * 32)
    request.user_id = user.user_id
    session.add(request)
    return request


def _request_expiry_not_after_creation(session: Session) -> None:
    _request(session).expires_time = NOW


def _empty_redirect_uri(session: Session) -> None:
    _request(session).redirect_uri = ""


def _over_long_redirect_uri(session: Session) -> None:
    _request(session).redirect_uri = "https://claude.ai/" + "x" * 2031


def _code_without_expiry(session: Session) -> None:
    _request(session).code_hash = b"c" * 32


def _code_expiry_without_code(session: Session) -> None:
    _request(session).code_expires_time = NOW + timedelta(seconds=60)


def _consumed_without_code(session: Session) -> None:
    _request(session).consumed_time = NOW


@pytest.mark.parametrize(
    "build_invalid_row",
    [
        _blank_client_id,
        _blank_created_ip,
        _blank_grant_key,
        _token_expiry_not_after_creation,
        _request_expiry_not_after_creation,
        _empty_redirect_uri,
        _over_long_redirect_uri,
        _code_without_expiry,
        _code_expiry_without_code,
        _consumed_without_code,
    ],
)
def test_additional_check_constraints_reject_invalid_rows(
    session: Session, build_invalid_row: Callable[[Session], None]
) -> None:
    build_invalid_row(session)

    _assert_rejected(session)


def test_maximum_length_redirect_uri_is_accepted(session: Session) -> None:
    _request(session).redirect_uri = "https://claude.ai/" + "x" * 2030
    session.commit()
