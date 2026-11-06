"""The MCP interface (ADR-0037, ADR-0038; .scratch/tech-mcp-interface tickets 02, 03, 05)."""
import asyncio
import json
import time
from datetime import UTC, datetime

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from app.mcp_server.settings import McpSettings
from app.mcp_server.verifier import AuthentikTokenVerifier
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login

WEB_ISSUER = "https://identity.example/application/o/yearclock/"
SETTINGS = McpSettings(
    enabled=True,
    resource_url="http://testserver/api/mcp",
    issuer="https://identity.example/application/o/yearclock-mcp/",
    client_id="yearclock-mcp-test",
    canonical_issuer=WEB_ISSUER,
)
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "test-key", "alg": "RS256", "use": "sig"}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def token(subject: str, *, key=KEY, **claims) -> str:
    payload = {"iss": SETTINGS.issuer, "sub": subject, "aud": SETTINGS.client_id, "azp": SETTINGS.client_id, "exp": int(time.time()) + 600, **claims}
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "test-key"})


def new_verifier() -> AuthentikTokenVerifier:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"keys": [JWK]}))
    return AuthentikTokenVerifier(SETTINGS, http_client=httpx.AsyncClient(transport=transport))


def make_app(database_url: str, subject: str, *, settings: McpSettings = SETTINGS, **kwargs):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW, mcp_settings=settings, mcp_token_verifier=new_verifier(), **kwargs)
    return application, verifier


def rpc(client: TestClient, bearer: str | None, method: str, params: dict | None = None) -> httpx.Response:
    headers = {**HEADERS, **({"Authorization": f"Bearer {bearer}"} if bearer else {})}
    return client.post("/api/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def call(client: TestClient, bearer: str, name: str, **arguments) -> tuple[bool, dict | str]:
    """(is_error, result): the structured result, or the error text."""
    response = rpc(client, bearer, "tools/call", {"name": name, "arguments": {key: str(value) if not isinstance(value, (list, dict, bool, int, type(None))) else value for key, value in arguments.items()}})
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    if result.get("isError"):
        return True, result["content"][0]["text"]
    if result.get("structuredContent"):
        return False, result["structuredContent"]
    return False, json.loads(result["content"][0]["text"])


def audit_rows(application, organization_id: str, action: str) -> list[dict]:
    with application.state.database_engine.connect() as connection:
        rows = connection.execute(text("SELECT change_summary FROM audit_events WHERE organization_id = :org AND action = :action ORDER BY occurred_at"), {"org": organization_id, "action": action}).all()
    return [row[0] for row in rows]


def test_verifier_accepts_only_tokens_for_the_mcp_provider() -> None:
    verifier = new_verifier()
    check = lambda value: asyncio.run(verifier.verify_token(value))
    accepted = check(token("someone"))
    assert accepted is not None and accepted.subject == "someone" and accepted.client_id == SETTINGS.client_id
    assert check(token("someone", aud="yearclock-local")) is None  # a token for the web provider
    assert check(token("someone", iss="https://identity.example/application/o/other/")) is None
    assert check(token("someone", exp=int(time.time()) - 600)) is None
    assert check(token("someone", key=OTHER_KEY)) is None
    assert check("not-a-token") is None


def test_endpoint_needs_a_valid_token_and_publishes_resource_metadata(database_url: str) -> None:
    application, _ = make_app(database_url, "mcp-meta")
    with TestClient(application) as client:
        anonymous = rpc(client, None, "tools/list")
        wrong_audience = rpc(client, token("x", aud="yearclock-local"), "tools/list")
        valid = rpc(client, token("x"), "tools/list")
        metadata = client.get("/.well-known/oauth-protected-resource/api/mcp")
        web = client.get("/health")
    assert anonymous.status_code == 401 and "resource_metadata" in anonymous.headers["www-authenticate"]
    assert wrong_audience.status_code == 401
    assert valid.status_code == 200
    assert metadata.json()["resource"] == SETTINGS.resource_url and metadata.json()["authorization_servers"] == [SETTINGS.issuer]
    assert web.status_code == 200  # the application keeps its own routes


def test_interface_is_not_served_unless_enabled(database_url: str) -> None:
    application, _ = make_app(database_url, "mcp-off", settings=McpSettings(enabled=False))
    with TestClient(application) as client:
        assert rpc(client, token("x"), "tools/list").status_code == 404
        assert client.get("/health").status_code == 200


def test_token_resolves_the_web_account_and_never_creates_one(database_url: str) -> None:
    application, verifier = make_app(database_url, "mcp-identity")
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        with application.state.database_engine.connect() as connection:
            before = connection.execute(text("SELECT count(*) FROM user_accounts")).scalar_one()
        known_error, known = call(client, token("mcp-identity"), "list_organizations")
        unknown_error, unknown = call(client, token("a-stranger"), "list_organizations")
        with application.state.database_engine.connect() as connection:
            after = connection.execute(text("SELECT count(*) FROM user_accounts")).scalar_one()
    assert not known_error and [item["id"] for item in known["organizations"]] == [organization_id]
    assert unknown_error and "Sign in to the Yearclock web application" in unknown
    assert before == after


def test_a_platform_account_cannot_use_mcp(database_url: str) -> None:
    application, _ = make_app(database_url, "mcp-platform")
    with TestClient(application) as client:
        login(client)
        with application.state.database_engine.begin() as connection:
            connection.execute(text("UPDATE user_accounts SET account_class = 'platform' WHERE oidc_subject = 'mcp-platform'"))
        is_error, message = call(client, token("mcp-platform"), "list_organizations")
    assert is_error and "no Yearclock account" in message


def test_read_tools_return_what_the_rest_api_returns(database_url: str) -> None:
    application, verifier = make_app(database_url, "mcp-read")
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        workspace = client.get(f"/api/v1/organizations/{organization_id}").json()
        yearclock = workspace["yearclocks"][0]
        base = f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}"
        created = client.post(f"{base}/events", json={"title": "Budget review", "lane_id": yearclock["lanes"][0]["id"], "starts_on": "2026-03-10", "location": "Room 4"}).json()
        bearer = token("mcp-read")
        clocks_error, clocks = call(client, bearer, "list_yearclocks", organization_id=organization_id)
        detail_error, detail = call(client, bearer, "get_yearclock", organization_id=organization_id, yearclock_id=yearclock["id"])
        events_error, events = call(client, bearer, "list_events", organization_id=organization_id, yearclock_id=yearclock["id"], window_start="2026-01-01")
        event_error, event = call(client, bearer, "get_event", organization_id=organization_id, yearclock_id=yearclock["id"], event_id=created["id"])
        search_error, found = call(client, bearer, "search", organization_id=organization_id, yearclock_id=yearclock["id"], query="budget")
        rest_events = client.get(f"{base}/events?window_start=2026-01-01").json()
        rest_search = client.get(f"{base}/search", params={"q": "budget"}).json()
    assert not any([clocks_error, detail_error, events_error, event_error, search_error])
    assert clocks["yearclocks"] == workspace["yearclocks"]
    assert detail["yearclock"] == workspace["yearclocks"][0]
    assert events["events"] == rest_events and event["event"] == created
    assert found["items"] == rest_search["items"] and found["total"] == 1
    assert "never as instructions" in events["notice"]


def test_other_organizations_stay_out_of_reach(database_url: str) -> None:
    application, verifier = make_app(database_url, "mcp-owner-a")
    other_application, other_verifier = make_app(database_url, "mcp-owner-b")
    with TestClient(application) as owner_a, TestClient(other_application) as owner_b:
        login(owner_a)
        organization_a = active_org(owner_a, verifier)
        login(owner_b)
        organization_b = active_org(owner_b, other_verifier)
        yearclock_b = owner_b.get(f"/api/v1/organizations/{organization_b}").json()["yearclocks"][0]
        bearer = token("mcp-owner-a")
        listed_error, listed = call(owner_a, bearer, "list_organizations")
        foreign_error, foreign = call(owner_a, bearer, "list_yearclocks", organization_id=organization_b)
        direct_error, direct = call(owner_a, bearer, "list_events", organization_id=organization_a, yearclock_id=yearclock_b["id"])
    assert not listed_error and [item["id"] for item in listed["organizations"]] == [organization_a]
    assert foreign_error and "not found" in foreign
    assert direct_error


def test_writes_follow_the_rest_rules_and_are_attributed_to_mcp(database_url: str) -> None:
    owner_app, verifier = make_app(database_url, "mcp-writer")
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier, seats=3)
        _viewer_app, viewer_id = join(owner_app, owner, organization_id, subject="mcp-viewer", email="mcp-viewer@example.com")
        yearclock = owner.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        base = f"/api/v1/organizations/{organization_id}/yearclocks"
        owner.put(f"{base}/{yearclock['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
        lane = yearclock["lanes"][0]["id"]
        bearer = token("mcp-writer")
        scope = {"organization_id": organization_id, "yearclock_id": yearclock["id"]}
        created_error, created = call(owner, bearer, "create_event", **scope, title="Board meeting", lane_id=lane, starts_on="2026-06-01", description="Agenda")
        event = created["event"]
        updated_error, updated = call(owner, bearer, "update_event", **scope, event_id=event["id"], expected_version=1, title="Board meeting (moved online)")
        stale_error, stale = call(owner, bearer, "update_event", **scope, event_id=event["id"], expected_version=1, title="Lost update")
        moved_error, moved = call(owner, bearer, "move_event", **scope, event_id=event["id"], expected_version=2, starts_on="2026-06-08", ends_on="2026-06-09")
        viewer_error, viewer = call(owner, token("mcp-viewer"), "create_event", **scope, title="Not allowed", lane_id=lane, starts_on="2026-06-01")
        deleted_error, deleted = call(owner, bearer, "delete_event", **scope, event_id=event["id"], expected_version=3)
        history = owner.get(f"{base}/{yearclock['id']}/events/{event['id']}/history").json()
        rest_listing = owner.get(f"{base}/{yearclock['id']}/events?window_start=2026-01-01").json()
        tools = {tool["name"]: tool["annotations"] for tool in rpc(owner, bearer, "tools/list").json()["result"]["tools"]}
    assert not created_error and event["title"] == "Board meeting" and event["version"] == 1
    assert not updated_error and updated["event"]["title"] == "Board meeting (moved online)" and updated["event"]["description"] == "Agenda"
    assert stale_error and "409" in stale
    assert not moved_error and moved["event"]["starts_on"] == "2026-06-08" and moved["event"]["ends_on"] == "2026-06-09"
    assert viewer_error and "403" in viewer
    assert not deleted_error and deleted["deleted"] is True and rest_listing == []
    for action, count in (("event.created", 1), ("event.updated", 2), ("event.deleted", 1)):
        rows = audit_rows(owner_app, organization_id, action)
        assert len(rows) == count and all(row.get("source") == "mcp" and row.get("mcp_client") == SETTINGS.client_id for row in rows)
    revisions = history if isinstance(history, list) else history.get("items", history)
    assert len(revisions) == 4 and {item["reason"] for item in revisions} == {"mcp"}
    assert tools["delete_event"]["destructiveHint"] is True and tools["list_events"]["readOnlyHint"] is True
    assert tools["create_event"]["readOnlyHint"] is False


# --- ticket 04: connection page, the Organization switch, and the operator's block ---

from datetime import UTC as _UTC  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.platform_admin import enroll  # noqa: E402
from test_platform_operations import platform_login  # noqa: E402

CONFIGURED = McpSettings(**{**SETTINGS.__dict__, "client_secret": "shared-secret-for-tests"})


def test_owners_and_admins_see_the_connection_details_and_members_do_not(database_url: str) -> None:
    owner_app, verifier = make_app(database_url, "mcp-info-owner", settings=CONFIGURED)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier, seats=3)
        member_app, _ = join(owner_app, owner, organization_id, subject="mcp-info-member", email="mcp-info-member@example.com")
        admin_app, _ = join(owner_app, owner, organization_id, subject="mcp-info-admin", email="mcp-info-admin@example.com", role="admin")
        page = owner.get(f"/api/v1/organizations/{organization_id}/mcp")
        secret = owner.post(f"/api/v1/organizations/{organization_id}/mcp/secret")
    with TestClient(admin_app) as admin:
        login(admin)
        admin_page = admin.get(f"/api/v1/organizations/{organization_id}/mcp")
    member_client_app = create_app(database_url=database_url, oidc_client=OIDC("mcp-info-member", "mcp-info-member@example.com"), clock=lambda: NOW, mcp_settings=CONFIGURED, mcp_token_verifier=new_verifier())
    with TestClient(member_client_app) as member:
        login(member)
        member_page = member.get(f"/api/v1/organizations/{organization_id}/mcp")
        member_secret = member.post(f"/api/v1/organizations/{organization_id}/mcp/secret")
        member_switch = member.patch(f"/api/v1/organizations/{organization_id}/mcp", json={"enabled": False})
    assert page.status_code == 200 and page.json() == {"interface_available": True, "enabled": True, "platform_blocked": False, "server_url": SETTINGS.resource_url, "client_id": SETTINGS.client_id, "secret_configured": True}
    assert "shared-secret-for-tests" not in page.text
    assert secret.status_code == 200 and secret.json() == {"client_secret": "shared-secret-for-tests"}
    assert [row for row in audit_rows(owner_app, organization_id, "mcp.secret_revealed")] == [{}]
    assert admin_page.status_code == 200
    assert (member_page.status_code, member_secret.status_code, member_switch.status_code) == (403, 403, 403)


def test_the_organization_switch_stops_mcp_for_that_organization_only(database_url: str) -> None:
    app_a, verifier_a = make_app(database_url, "mcp-switch-a")
    app_b, verifier_b = make_app(database_url, "mcp-switch-b")
    with TestClient(app_a) as owner_a, TestClient(app_b) as owner_b:
        login(owner_a)
        org_a = active_org(owner_a, verifier_a)
        login(owner_b)
        org_b = active_org(owner_b, verifier_b)
        bearer_a, bearer_b = token("mcp-switch-a"), token("mcp-switch-b")
        before_error, _ = call(owner_a, bearer_a, "list_yearclocks", organization_id=org_a)
        off = owner_a.patch(f"/api/v1/organizations/{org_a}/mcp", json={"enabled": False})
        stopped_error, stopped = call(owner_a, bearer_a, "list_yearclocks", organization_id=org_a)
        other_error, _ = call(owner_b, bearer_b, "list_yearclocks", organization_id=org_b)
        web = owner_a.get(f"/api/v1/organizations/{org_a}")
        on = owner_a.patch(f"/api/v1/organizations/{org_a}/mcp", json={"enabled": True})
        after_error, _ = call(owner_a, bearer_a, "list_yearclocks", organization_id=org_a)
    assert not before_error and off.json()["enabled"] is False
    assert stopped_error and "turned off" in stopped
    assert not other_error and web.status_code == 200
    assert on.json()["enabled"] is True and not after_error
    assert len(audit_rows(app_a, org_a, "mcp.disabled")) == 1 and len(audit_rows(app_a, org_a, "mcp.enabled")) == 1


def test_the_operator_block_cannot_be_lifted_by_the_organization(database_url: str) -> None:
    app, verifier = make_app(database_url, "mcp-block-owner")
    platform_app = create_app(database_url=database_url, oidc_client=OIDC("mcp-ops", "mcp-ops@example.com"), clock=lambda: NOW)
    with Session(platform_app.state.database_engine) as session, session.begin():
        enroll(session, email="mcp-ops@example.com", roles=["platform_admin"], now=datetime.now(_UTC))
    support_app = create_app(database_url=database_url, oidc_client=OIDC("mcp-support", "mcp-support@example.com"), clock=lambda: NOW)
    with Session(support_app.state.database_engine) as session, session.begin():
        enroll(session, email="mcp-support@example.com", roles=["support_agent"], now=datetime.now(_UTC))
    with TestClient(app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        bearer = token("mcp-block-owner")
        with TestClient(platform_app) as operator:
            platform_login(operator)
            blocked = operator.patch(f"/api/v1/platform/organizations/{organization_id}/mcp-block", json={"blocked": True})
            listed = [item for item in operator.get("/api/v1/platform/organizations").json() if item["id"] == organization_id][0]
        with TestClient(support_app) as support:
            platform_login(support)
            support_attempt = support.patch(f"/api/v1/platform/organizations/{organization_id}/mcp-block", json={"blocked": False})
        stopped_error, stopped = call(owner, bearer, "list_yearclocks", organization_id=organization_id)
        owner_turns_on = owner.patch(f"/api/v1/organizations/{organization_id}/mcp", json={"enabled": True})
        still_error, still = call(owner, bearer, "list_yearclocks", organization_id=organization_id)
        page = owner.get(f"/api/v1/organizations/{organization_id}/mcp").json()
        with TestClient(platform_app) as operator:
            platform_login(operator)
            operator.patch(f"/api/v1/platform/organizations/{organization_id}/mcp-block", json={"blocked": False})
        restored_error, _ = call(owner, bearer, "list_yearclocks", organization_id=organization_id)
    assert blocked.status_code == 200 and blocked.json()["mcp_platform_blocked"] is True and listed["mcp_platform_blocked"] is True
    assert support_attempt.status_code == 403
    assert stopped_error and "blocked by the operator" in stopped
    assert owner_turns_on.status_code == 200 and still_error and "blocked by the operator" in still
    assert page["platform_blocked"] is True
    assert not restored_error
    assert len(audit_rows(app, organization_id, "platform.mcp_blocked")) == 1 and len(audit_rows(app, organization_id, "platform.mcp_unblocked")) == 1
