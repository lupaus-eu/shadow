"""The MCP interface (ADR-0037, ADR-0038; .scratch/tech-mcp-interface tickets 02, 03, 05)."""
import asyncio
import json
import time
from uuid import UUID
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

WEB_ISSUER = "https://identity.example/application/o/shadow/"
SETTINGS = McpSettings(
    enabled=True,
    resource_url="http://testserver/api/mcp",
    issuer="https://identity.example/application/o/shadow-mcp/",
    client_id="shadow-mcp-test",
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


def call(client: TestClient, bearer: str, name: str, /, **arguments) -> tuple[bool, dict | str]:
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
    assert check(token("someone", aud="shadow-local")) is None  # a token for the web provider
    assert check(token("someone", iss="https://identity.example/application/o/other/")) is None
    assert check(token("someone", exp=int(time.time()) - 600)) is None
    assert check(token("someone", key=OTHER_KEY)) is None
    assert check("not-a-token") is None


def test_endpoint_needs_a_valid_token_and_publishes_resource_metadata(database_url: str) -> None:
    application, _ = make_app(database_url, "mcp-meta")
    with TestClient(application) as client:
        anonymous = rpc(client, None, "tools/list")
        wrong_audience = rpc(client, token("x", aud="shadow-local"), "tools/list")
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
    assert unknown_error and "Sign in to the Shadow web application" in unknown
    assert before == after


def test_a_platform_account_cannot_use_mcp(database_url: str) -> None:
    application, _ = make_app(database_url, "mcp-platform")
    with TestClient(application) as client:
        login(client)
        with application.state.database_engine.begin() as connection:
            connection.execute(text("UPDATE user_accounts SET account_class = 'platform' WHERE oidc_subject = 'mcp-platform'"))
        is_error, message = call(client, token("mcp-platform"), "list_organizations")
    assert is_error and "no Shadow account" in message


def test_other_organizations_stay_out_of_reach(database_url: str) -> None:
    application, verifier = make_app(database_url, "mcp-owner-a")
    other_application, other_verifier = make_app(database_url, "mcp-owner-b")
    with TestClient(application) as owner_a, TestClient(other_application) as owner_b:
        login(owner_a)
        organization_a = active_org(owner_a, verifier)
        login(owner_b)
        organization_b = active_org(owner_b, other_verifier)
        
        bearer = token("mcp-owner-a")
        listed_error, listed = call(owner_a, bearer, "list_organizations")
        foreign_error, foreign = call(owner_a, bearer, "get_organization", organization_id=organization_b)
    assert not listed_error and [item["id"] for item in listed["organizations"]] == [organization_a]
    assert foreign_error and "not found" in foreign


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
        before_error, _ = call(owner_a, bearer_a, "get_organization", organization_id=org_a)
        off = owner_a.patch(f"/api/v1/organizations/{org_a}/mcp", json={"enabled": False})
        stopped_error, stopped = call(owner_a, bearer_a, "get_organization", organization_id=org_a)
        other_error, _ = call(owner_b, bearer_b, "get_organization", organization_id=org_b)
        web = owner_a.get(f"/api/v1/organizations/{org_a}")
        on = owner_a.patch(f"/api/v1/organizations/{org_a}/mcp", json={"enabled": True})
        after_error, _ = call(owner_a, bearer_a, "get_organization", organization_id=org_a)
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
        stopped_error, stopped = call(owner, bearer, "get_organization", organization_id=organization_id)
        owner_turns_on = owner.patch(f"/api/v1/organizations/{organization_id}/mcp", json={"enabled": True})
        still_error, still = call(owner, bearer, "get_organization", organization_id=organization_id)
        page = owner.get(f"/api/v1/organizations/{organization_id}/mcp").json()
        with TestClient(platform_app) as operator:
            platform_login(operator)
            operator.patch(f"/api/v1/platform/organizations/{organization_id}/mcp-block", json={"blocked": False})
        restored_error, _ = call(owner, bearer, "get_organization", organization_id=organization_id)
    assert blocked.status_code == 200 and blocked.json()["mcp_platform_blocked"] is True and listed["mcp_platform_blocked"] is True
    assert support_attempt.status_code == 403
    assert stopped_error and "blocked by the operator" in stopped
    assert owner_turns_on.status_code == 200 and still_error and "blocked by the operator" in still
    assert page["platform_blocked"] is True
    assert not restored_error
    assert len(audit_rows(app, organization_id, "platform.mcp_blocked")) == 1 and len(audit_rows(app, organization_id, "platform.mcp_unblocked")) == 1


def test_agents_work_with_models_through_the_same_rules(database_url: str) -> None:
    application, verifier = make_app(database_url, "mcp-models")
    with TestClient(application) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        bearer = token("mcp-models")
        names = {tool["name"] for tool in rpc(owner, bearer, "tools/list").json()["result"]["tools"]}
        assert {"create_model", "get_model", "run_simulation", "generate_analysis", "set_metric_values"} <= names
        _, created = call(owner, bearer, "create_model", organization_id=organization_id, name="Agent twin")
        model_id = created["result"]["id"]
        _, graph = call(owner, bearer, "get_model", organization_id=organization_id, model_id=model_id)
        version_id = graph["result"]["line"]["id"]
        types = {item["key"]: item["id"] for item in graph["result"]["node_types"]} | {f"c:{item['key']}": item["id"] for item in graph["result"]["connection_types"]}
        event = graph["result"]["latest_event"]
        failed, message = call(owner, bearer, "create_node", organization_id=organization_id, model_id=model_id, event_id=event["id"], node_type_id=types["product"], name="  ")
        assert failed and "name" in message
        ok, node = call(owner, bearer, "create_node", organization_id=organization_id, model_id=model_id, event_id=event["id"], node_type_id=types["product"], name="App", expected_version=event["version"])
        assert not ok and node["result"]["node"]["name"] == "App" and node["result"]["id"] == node["result"]["node"]["id"]
        stale, message = call(owner, bearer, "create_node", organization_id=organization_id, model_id=model_id, event_id=event["id"], node_type_id=types["journey"], name="Late", expected_version=event["version"])
        assert stale and "409" in message  # the first edit moved the event on
        _, journey = call(owner, bearer, "create_node", organization_id=organization_id, model_id=model_id, event_id=event["id"], node_type_id=types["journey"], name="Onboarding")
        link = {"connection_type_id": types["c:features_in"], "source_node_id": node["result"]["id"], "target_node_id": journey["result"]["id"]}
        assert not call(owner, bearer, "create_connection", organization_id=organization_id, model_id=model_id, event_id=event["id"], **link)[0]
        refused, reason = call(owner, bearer, "create_connection", organization_id=organization_id, model_id=model_id, event_id=event["id"], **link)
        assert refused and "chain_broken" in reason and "duplicate_connection" in reason  # nothing was saved
        _, after = call(owner, bearer, "get_model", organization_id=organization_id, model_id=model_id)
        assert {item["name"] for item in after["result"]["nodes"]} == {"App", "Onboarding"} and len(after["result"]["connections"]) == 1
        assert after["result"]["latest_event"]["id"] == event["id"]
        _, metric = call(owner, bearer, "create_metric", organization_id=organization_id, model_id=model_id, line_id=version_id, key="revenue", name="Revenue")
        values = [{"period": f"2025-{month:02d}-01", "value": 100 + month * 10} for month in range(1, 13)]
        assert not call(owner, bearer, "set_metric_values", organization_id=organization_id, model_id=model_id, line_id=version_id, metric_id=metric["result"]["id"], values=values)[0]
        _, run = call(owner, bearer, "run_simulation", organization_id=organization_id, model_id=model_id, line_id=version_id, name="Plan", horizon_months=6)
        simulation_id = run["result"]["simulation"]["id"]
        _, analysis = call(owner, bearer, "generate_analysis", organization_id=organization_id, model_id=model_id, simulation_id=simulation_id)
        assert analysis["result"]["findings"]
        _, series = call(owner, bearer, "get_metric_series", organization_id=organization_id, model_id=model_id, line_id=version_id, metric_id=metric["result"]["id"])
        assert len(series["result"]["points"]) == 12
    audit = audit_rows(application, organization_id, "event.updated")
    assert len(audit) == 3 and all(row["fields"] == ["changes"] and row["source"] == "mcp" for row in audit)  # two nodes and a connection, written as changes of the event
    assert audit[-1]["change_counts"] == {"add_connection": 1, "add_node": 2} and "App" not in json.dumps(audit)


def test_agents_read_and_write_lines_events_and_adopt_scenarios_under_the_same_rules(database_url: str) -> None:
    application, verifier = make_app(database_url, "mcp-lines")
    with TestClient(application) as owner:
        login(owner)
        organization_id = active_org(owner, verifier, seats=3)
        join(application, owner, organization_id, subject="mcp-lines-member", email="mcp-lines-member@example.com")
        bearer, member = token("mcp-lines"), token("mcp-lines-member")
        names = {tool["name"] for tool in rpc(owner, bearer, "tools/list").json()["result"]["tools"]}
        assert {"list_lines", "list_events", "get_state", "create_scenario", "add_event", "update_event", "delete_event", "adopt_scenario"} <= names
        assert not names & {"create_version", "merge_version", "get_version_changes"}
        _, created = call(owner, bearer, "create_model", organization_id=organization_id, name="Line twin")
        model_id = created["result"]["id"]
        with application.state.database_engine.begin() as connection:  # the initial event is dated the creation day; the agent writes earlier history
            connection.execute(text("UPDATE timeline_events SET occurred_on = '2025-12-31' WHERE model_id = :id"), {"id": model_id})
        _, graph = call(owner, bearer, "get_model", organization_id=organization_id, model_id=model_id)
        types = {item["key"]: item["id"] for item in graph["result"]["node_types"]} | {f"c:{item['key']}": item["id"] for item in graph["result"]["connection_types"]}
        _, listed = call(owner, bearer, "list_lines", organization_id=organization_id, model_id=model_id)
        base = listed["result"][0]
        assert [item["kind"] for item in listed["result"]] == ["base"] and base["id"] == graph["result"]["line"]["id"] == created["result"]["base_line_id"]
        node = lambda name, kind="product": {"op": "add_node", "payload": {"node_type_id": types[kind], "name": name}}  # noqa: E731
        # Writes follow the roles: Members do not write the Base line, the Owner does; a broken chain is refused with its reason.
        denied, message = call(owner, member, "add_event", organization_id=organization_id, model_id=model_id, line_id=base["id"], occurred_on="2026-01-10", title="Member try", changes=[node("Nope")])
        assert denied and "403" in message
        broken, message = call(owner, bearer, "add_event", organization_id=organization_id, model_id=model_id, line_id=base["id"], occurred_on="2026-01-10", title="Broken", changes=[{"op": "update_node", "element_id": "00000000-0000-0000-0000-0000000000aa", "payload": {"name": "Ghost"}}])
        assert broken and "chain_broken" in message and "missing_element" in message
        ok, start = call(owner, bearer, "add_event", organization_id=organization_id, model_id=model_id, line_id=base["id"], occurred_on="2026-01-10", title="Start", note="First", changes=[node("App"), node("Onboarding", "journey")])
        assert not ok and start["result"]["title"] == "Start" and start["result"]["change_counts"] == {"add_node": 2}
        _, events = call(owner, bearer, "list_events", organization_id=organization_id, model_id=model_id, line_id=base["id"])
        assert [item["title"] for item in events["result"]] == ["Initial situation", "Start"] and events["result"][1]["planned"] is False
        _, by_event = call(owner, bearer, "get_state", organization_id=organization_id, model_id=model_id, line_id=base["id"], event_id=start["result"]["id"])
        assert {item["name"] for item in by_event["result"]["nodes"]} == {"App", "Onboarding"} and len(by_event["result"]["added"]["nodes"]) == 2
        _, before = call(owner, bearer, "get_state", organization_id=organization_id, model_id=model_id, line_id=base["id"], as_of="2026-01-09")
        _, after = call(owner, bearer, "get_state", organization_id=organization_id, model_id=model_id, line_id=base["id"], as_of="2026-01-10")
        assert before["result"]["nodes"] == [] and len(after["result"]["nodes"]) == 2
        both, message = call(owner, bearer, "get_state", organization_id=organization_id, model_id=model_id, line_id=base["id"], event_id=start["result"]["id"], as_of="2026-01-10")
        assert both and "event_id_and_as_of" in message
        # A Member makes a Scenario and writes to it; a stale update is refused; events can be changed and deleted.
        ok, scenario = call(owner, member, "create_scenario", organization_id=organization_id, model_id=model_id, name="Grow", branch_event_id=start["result"]["id"])
        assert not ok and scenario["result"]["kind"] == "scenario" and scenario["result"]["parent_line_id"] == base["id"]
        ok, plan = call(owner, member, "add_event", organization_id=organization_id, model_id=model_id, line_id=scenario["result"]["id"], occurred_on="2026-03-01", title="Hire", changes=[node("Ada", "person")])
        assert not ok
        ok, extra = call(owner, member, "add_event", organization_id=organization_id, model_id=model_id, line_id=scenario["result"]["id"], occurred_on="2026-04-01", title="Extra", changes=[])
        stale, message = call(owner, member, "update_event", organization_id=organization_id, model_id=model_id, event_id=plan["result"]["id"], expected_version=7, title="Hire people")
        assert stale and "409" in message
        ok, renamed = call(owner, member, "update_event", organization_id=organization_id, model_id=model_id, event_id=plan["result"]["id"], expected_version=1, title="Hire people", note="")
        assert not ok and renamed["result"]["title"] == "Hire people" and renamed["result"]["note"] is None and renamed["result"]["version"] == 2
        ok, moved = call(owner, member, "update_event", organization_id=organization_id, model_id=model_id, event_id=extra["result"]["id"], expected_version=1, occurred_on="2026-05-01")
        assert not ok and moved["result"]["occurred_on"] == "2026-05-01"
        branch_blocked, message = call(owner, bearer, "delete_event", organization_id=organization_id, model_id=model_id, event_id=start["result"]["id"], expected_version=1)
        assert branch_blocked and "branch_point" in message  # the Scenario starts from it
        ok, deleted = call(owner, member, "delete_event", organization_id=organization_id, model_id=model_id, event_id=extra["result"]["id"], expected_version=2)
        assert not ok and deleted["result"] == {"deleted_event_id": extra["result"]["id"]}
        # Adopting into the Base line is for Owners and Admins; refused data comes back readable; the Scenario goes away.
        member_adopt, message = call(owner, member, "adopt_scenario", organization_id=organization_id, model_id=model_id, line_id=scenario["result"]["id"])
        assert member_adopt and "403" in message
        ok, adopted = call(owner, bearer, "adopt_scenario", organization_id=organization_id, model_id=model_id, line_id=scenario["result"]["id"], expected_version=1)
        assert not ok and adopted["result"]["scenario"] is None and [item["title"] for item in adopted["result"]["adopted_events"]] == ["Hire people"]
        _, lines_after = call(owner, bearer, "list_lines", organization_id=organization_id, model_id=model_id)
        assert [item["id"] for item in lines_after["result"]] == [base["id"]] and lines_after["result"][0]["event_count"] == 3
        _, present = call(owner, bearer, "get_state", organization_id=organization_id, model_id=model_id, line_id=base["id"])
        assert {item["name"] for item in present["result"]["nodes"]} == {"App", "Onboarding", "Ada"}
        # A read-only Organization can still be read through the tools but not written.
        with application.state.database_engine.begin() as connection:
            connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
        blocked, message = call(owner, bearer, "add_event", organization_id=organization_id, model_id=model_id, line_id=base["id"], occurred_on="2026-06-01", title="Blocked")
        assert blocked and "read-only" in message
        blocked_scenario, _ = call(owner, bearer, "create_scenario", organization_id=organization_id, model_id=model_id, name="Blocked", branch_event_id=start["result"]["id"])
        assert blocked_scenario and not call(owner, bearer, "list_events", organization_id=organization_id, model_id=model_id, line_id=base["id"])[0]
    for action, count in (("event.created", 3), ("event.updated", 2), ("event.deleted", 1), ("line.created", 1), ("line.adopted", 1)):
        rows = audit_rows(application, organization_id, action)
        assert len(rows) == count and all(row["source"] == "mcp" for row in rows), action
    assert "Secret" not in json.dumps(audit_rows(application, organization_id, "line.adopted"))
    rows = call_rows(application, organization_id)
    kinds = {row["tool"]: row["kind"] for row in rows}
    assert kinds["list_lines"] == kinds["list_events"] == kinds["get_state"] == "read"
    assert kinds["create_scenario"] == kinds["add_event"] == kinds["update_event"] == kinds["delete_event"] == kinds["adopt_scenario"] == "write"
    assert ("add_event", "refused", "read_only") in {(row["tool"], row["outcome"], row["reason"]) for row in rows} and ("add_event", "refused", "forbidden") in {(row["tool"], row["outcome"], row["reason"]) for row in rows}
    assert "Grow" not in json.dumps(rows) and "Hire" not in json.dumps(rows)


def test_agents_write_a_summary_and_proposals_under_their_own_label(database_url: str) -> None:
    application, verifier = make_app(database_url, "mcp-analysis")
    with TestClient(application) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        bearer = token("mcp-analysis")
        names = {tool["name"] for tool in rpc(owner, bearer, "tools/list").json()["result"]["tools"]}
        assert {"set_analysis_summary", "add_proposal"} <= names
        _, created = call(owner, bearer, "create_model", organization_id=organization_id, name="Agent twin")
        model_id = created["result"]["id"]
        _, graph = call(owner, bearer, "get_model", organization_id=organization_id, model_id=model_id)
        version_id = graph["result"]["line"]["id"]
        _, metric = call(owner, bearer, "create_metric", organization_id=organization_id, model_id=model_id, line_id=version_id, key="revenue", name="Revenue")
        values = [{"period": f"2025-{month:02d}-01", "value": 100 - month * 3} for month in range(1, 13)]
        call(owner, bearer, "set_metric_values", organization_id=organization_id, model_id=model_id, line_id=version_id, metric_id=metric["result"]["id"], values=values)
        _, run = call(owner, bearer, "run_simulation", organization_id=organization_id, model_id=model_id, line_id=version_id, name="Plan", horizon_months=6)
        simulation_id = run["result"]["simulation"]["id"]
        failed, _ = call(owner, bearer, "set_analysis_summary", organization_id=organization_id, model_id=model_id, simulation_id=simulation_id, text="")
        assert failed
        failed, message = call(owner, bearer, "add_proposal", organization_id=organization_id, model_id=model_id, simulation_id=simulation_id, metric_key="ghost", title="t", rationale="r")
        assert failed and "404" in message
        failed, _ = call(owner, bearer, "add_proposal", organization_id=organization_id, model_id=model_id, simulation_id=simulation_id, metric_key="revenue", title="t", rationale="r", severity="urgent")
        assert failed
        ok, summary = call(owner, bearer, "set_analysis_summary", organization_id=organization_id, model_id=model_id, simulation_id=simulation_id, text="Revenue falls.")
        assert not ok and summary["result"]["summary"] == "Revenue falls." and summary["result"]["summary_author"] == f"agent:{SETTINGS.client_id}"
        ok, proposal = call(owner, bearer, "add_proposal", organization_id=organization_id, model_id=model_id, simulation_id=simulation_id, metric_key="revenue", title="Protect revenue", rationale="Down.", severity="high")
        assert not ok and proposal["result"]["kind"] == "agent"
        _, read = call(owner, bearer, "get_analysis", organization_id=organization_id, model_id=model_id, simulation_id=simulation_id)
        assert read["result"]["summary_author"] == f"agent:{SETTINGS.client_id}"
        assert [(item["kind"], item["metric_key"]) for item in read["result"]["recommendations"]] == [("agent", "revenue")]
    audit = audit_rows(application, organization_id, "analysis.summary_set")
    assert len(audit) == 1 and audit[0]["source"] == "mcp" and "Revenue falls." not in json.dumps(audit)
    assert len(audit_rows(application, organization_id, "analysis.proposal_set")) == 1


def call_rows(application, organization_id: str | None = None, person: str | None = None) -> list[dict]:
    where = "organization_id = :org" if organization_id else "organization_id IS NULL AND user_account_id = :person"
    with application.state.database_engine.connect() as connection:
        rows = connection.execute(text(f"SELECT tool, kind, outcome, reason, mcp_client, user_account_id::text, organization_id::text FROM mcp_calls WHERE {where} ORDER BY occurred_at"), {"org": organization_id, "person": person}).mappings().all()
    return [dict(row) for row in rows]


def test_every_agent_call_is_recorded_without_its_content(database_url: str) -> None:
    application, verifier = make_app(database_url, "mcp-calls")
    with TestClient(application) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        person = owner.get("/api/v1/auth/session").json()["user_account"]["id"]
        bearer = token("mcp-calls")
        call(owner, bearer, "list_organizations")
        call(owner, bearer, "get_organization", organization_id=organization_id)
        _, created = call(owner, bearer, "create_model", organization_id=organization_id, name="DISTINCTIVE-MODEL-NAME")
        model_id = created["result"]["id"]
        call(owner, bearer, "create_node", organization_id=organization_id, model_id=model_id, event_id="00000000-0000-0000-0000-000000000000", node_type_id="00000000-0000-0000-0000-000000000000", name="  ")
        call(owner, bearer, "get_model", organization_id=organization_id, model_id="00000000-0000-0000-0000-000000000000")
        owner.patch(f"/api/v1/organizations/{organization_id}/mcp", json={"enabled": False})
        call(owner, bearer, "get_organization", organization_id=organization_id)
        owner.patch(f"/api/v1/organizations/{organization_id}/mcp", json={"enabled": True})
        stranger = "00000000-0000-0000-0000-0000000000aa"
        call(owner, bearer, "get_organization", organization_id=stranger)
        page = owner.get(f"/api/v1/organizations/{organization_id}/mcp-calls")
    rows = call_rows(application, organization_id)
    assert [(row["tool"], row["kind"], row["outcome"], row["reason"]) for row in rows] == [
        ("get_organization", "read", "ok", None),
        ("create_model", "write", "ok", None),
        ("create_node", "write", "error", "invalid_input"),
        ("get_model", "read", "error", "http_404"),
        ("get_organization", "read", "refused", "switch_off"),
    ]
    assert all(row["user_account_id"] == person and row["mcp_client"] == SETTINGS.client_id for row in rows)
    assert not any(row["tool"] == "list_organizations" for row in rows) and call_rows(application, person=person) == [
        {"tool": "get_organization", "kind": "read", "outcome": "refused", "reason": "not_member", "mcp_client": SETTINGS.client_id, "user_account_id": person, "organization_id": None}
    ]
    assert "DISTINCTIVE" not in json.dumps(rows) and "DISTINCTIVE" not in page.text
    assert page.status_code == 200 and [item["tool"] for item in page.json()["items"]][0] == "get_organization"
    assert page.json()["items"][0]["person"] and page.json()["items"][0]["mcp_client"] == SETTINGS.client_id


def test_a_failed_record_stops_writes_but_not_reads(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.mcp_server.calls as calls

    application, verifier = make_app(database_url, "mcp-calls-fail")
    with TestClient(application) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        bearer = token("mcp-calls-fail")
        monkeypatch.setattr(calls, "_write", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit down")))
        read_failed, read = call(owner, bearer, "get_organization", organization_id=organization_id)
        write_failed, message = call(owner, bearer, "create_model", organization_id=organization_id, name="Unrecorded")
    assert not read_failed and read["notice"]
    assert write_failed and "could not be recorded" in message


def test_only_owners_and_admins_read_the_agent_calls(database_url: str) -> None:
    application, verifier = make_app(database_url, "mcp-calls-roles")
    with TestClient(application) as owner:
        login(owner)
        organization_id = active_org(owner, verifier, seats=3)
        member_app, _ = join(application, owner, organization_id, subject="mcp-calls-member", email="mcp-calls-member@example.com")
        admin_app, _ = join(application, owner, organization_id, subject="mcp-calls-admin", email="mcp-calls-admin@example.com", role="admin")
        assert owner.get(f"/api/v1/organizations/{organization_id}/mcp-calls").status_code == 200
    with TestClient(admin_app) as admin:
        login(admin)
        assert admin.get(f"/api/v1/organizations/{organization_id}/mcp-calls").status_code == 200
    with TestClient(member_app) as member:
        login(member)
        assert member.get(f"/api/v1/organizations/{organization_id}/mcp-calls").status_code == 403


def test_the_cleanup_deletes_only_old_successful_reads(database_url: str) -> None:
    from app.database import create_session_factory
    from app.jobs import run_one_background_job, schedule_mcp_read_log_cleanup_jobs

    application, verifier = make_app(database_url, "mcp-calls-cleanup")
    with TestClient(application) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        person = owner.get("/api/v1/auth/session").json()["user_account"]["id"]
    insert = text("INSERT INTO mcp_calls (id, organization_id, user_account_id, mcp_client, tool, kind, outcome, duration_ms, occurred_at) VALUES (gen_random_uuid(), :org, :person, 'c', :tool, :kind, :outcome, 5, now() - make_interval(days => :age))")
    with application.state.database_engine.begin() as connection:
        for tool, kind, outcome, age in [("old_read", "read", "ok", 100), ("new_read", "read", "ok", 10), ("old_failed_read", "read", "error", 100), ("old_write", "write", "ok", 100), ("old_refused", "read", "refused", 100)]:
            connection.execute(insert, {"org": organization_id, "person": person, "tool": tool, "kind": kind, "outcome": outcome, "age": age})
    factory = create_session_factory(application.state.database_engine)
    assert schedule_mcp_read_log_cleanup_jobs(factory, today=NOW.date()) >= 1
    while run_one_background_job(factory, organization_id=UUID(organization_id)):
        pass
    kept = {row["tool"] for row in call_rows(application, organization_id)}
    assert kept == {"new_read", "old_failed_read", "old_write", "old_refused"}
    # the application role may delete nothing else
    with application.state.database_engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE shadow_app"))
        connection.execute(text("SELECT set_config('app.current_organization_id', :org, true)"), {"org": organization_id})
        assert connection.execute(text("DELETE FROM mcp_calls WHERE tool = 'old_write'")).rowcount == 0
