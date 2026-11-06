"""Full authorization matrix across Organization, Yearclock, and platform roles (ticket 23, ADR-0007).

Every actor calls every representative endpoint against Organization A. The
expected status encodes the role model: Owner ⊇ Admin ⊇ Member; per-Yearclock
Editor and Viewer grants; Platform Users never reach customer routes; an
Owner of another Organization is a stranger to A. Mutations that succeed are
arranged so repeating them is harmless.
"""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from datetime import timedelta

from app.billing import CancelResult, PortalSession, SeatIncreasePreview
from app.database import RequestContext, create_session_factory, transaction_session
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login
from test_platform_operations import _platform_app, platform_login

ACTORS = ("owner", "admin", "editor", "viewer", "member", "stranger", "platform_admin", "support_agent")
ALLOWED, DENIED = "allowed", "denied"


class MatrixStripe(Stripe):
    """Answers the billing calls only an Owner should ever reach."""

    def preview_seat_increase(self, request):
        return SeatIncreasePreview(id="preview", amount_due=3000, currency="eur", proration_date=NOW)

    def create_portal_session(self, *, customer_id, return_url):
        return PortalSession(url="https://billing.stripe.test/session")

    def update_customer(self, *, customer_id, name, email):
        return None

    def set_cancel_at_period_end(self, *, subscription_id, cancel, schedule_id=None):
        return CancelResult(cancel_at_period_end=cancel, current_period_end=NOW + timedelta(days=20))


@pytest.fixture(scope="module")
def world(database_url):
    with ExitStack() as stack:
        verifier = Verifier()
        owner_app = create_app(database_url=database_url, oidc_client=OIDC("matrix-owner", "matrix-owner@example.com"), stripe_billing=MatrixStripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
        owner = stack.enter_context(TestClient(owner_app))
        login(owner)
        organization_id = active_org(owner, verifier, seats=6)
        clock = owner.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        base = f"/api/v1/organizations/{organization_id}"
        event = owner.post(f"{base}/yearclocks/{clock['id']}/events", json={"title": "Board meeting", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01"}).json()
        label = owner.post(f"{base}/labels", json={"name": "Matrix fixture", "color": "#1f5f99"}).json()
        other_label = owner.post(f"{base}/labels", json={"name": "Matrix other", "color": "#1f5f99"}).json()
        org_category = owner.post(f"{base}/categories", json={"name": "Matrix fixture", "color": "#1f5f99"}).json()
        clients = {"owner": owner}
        users = {}
        for actor, role in (("admin", "admin"), ("editor", "member"), ("viewer", "member"), ("member", "member")):
            application, user_id = join(owner_app, owner, organization_id, subject=f"matrix-{actor}", email=f"matrix-{actor}@example.com", role=role)
            clients[actor] = stack.enter_context(TestClient(application))
            login(clients[actor])
            users[actor] = user_id
        for actor in ("editor", "viewer"):
            assert owner.put(f"{base}/yearclocks/{clock['id']}/access", json={"user_account_id": users[actor], "role": actor}).status_code == 200
        # A second Yearclock that the Editor may read, as a source for copying and Linked Lanes (V2 P3).
        source_clock = owner.post(f"{base}/yearclocks", json={"name": "Matrix source"}).json()
        revision = owner.get(f"{base}/yearclocks/{clock['id']}/events/{event['id']}/history").json()["items"][-1]
        group = owner.post(f"{base}/groups", json={"name": "Matrix group"}).json()
        assert owner.put(f"{base}/yearclocks/{source_clock['id']}/access", json={"user_account_id": users["editor"], "role": "viewer"}).status_code == 200
        stranger_verifier = Verifier()
        stranger_app = create_app(database_url=database_url, oidc_client=OIDC("matrix-stranger", "matrix-stranger@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=stranger_verifier, clock=lambda: NOW)
        clients["stranger"] = stack.enter_context(TestClient(stranger_app))
        login(clients["stranger"])
        stranger_org = active_org(clients["stranger"], stranger_verifier)
        for actor in ("platform_admin", "support_agent"):
            clients[actor] = stack.enter_context(TestClient(_platform_app(database_url, f"matrix-{actor}", actor)))
            platform_login(clients[actor])
        memberships = {item["email"].split("@")[0].removeprefix("matrix-"): item for item in owner.get(f"{base}/memberships").json()}
        yield {"clients": clients, "base": base, "clock": clock, "event": event, "label": label, "other_label": other_label, "org_category": org_category, "memberships": memberships, "source_clock": source_clock, "revision": revision, "group": group, "organization_id": organization_id, "stranger_org": stranger_org, "engine": owner_app.state.database_engine}


def _event_body(world, title):
    return {"title": title, "lane_id": world["clock"]["lanes"][0]["id"], "starts_on": "2026-10-05"}


# Each case: name, callable(world, client) -> response, set of actors allowed.
CASES = [
    ("open workspace", lambda w, c: c.get(w["base"]), {"owner", "admin", "editor", "viewer", "member"}),
    ("read Events", lambda w, c: c.get(f"{w['base']}/yearclocks/{w['clock']['id']}/events"), {"owner", "admin", "editor", "viewer"}),
    ("export Events", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/export", json={"format": "csv", "scope": "all"}), {"owner", "admin", "editor", "viewer"}),
    ("download the import template", lambda w, c: c.get(f"{w['base']}/yearclocks/{w['clock']['id']}/import/template"), {"owner", "admin", "editor", "viewer"}),
    ("preview an import", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/import", params={"format": "csv", "dry_run": "true"}, content=b"Title,Starts,Lane\r\nMatrix,2026-10-09,General\r\n"), {"owner", "admin", "editor"}),
    ("search Events", lambda w, c: c.get(f"{w['base']}/yearclocks/{w['clock']['id']}/search", params={"q": "board"}), {"owner", "admin", "editor", "viewer"}),
    ("create Event", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/events", json=_event_body(w, "Matrix")), {"owner", "admin", "editor"}),
    ("create Category", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/categories", json={"name": "Matrix", "color": "#336699"}), {"owner", "admin", "editor"}),
    ("create Lane", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/lanes", json={"name": "Matrix"}), {"owner", "admin", "editor"}),
    ("create Yearclock", lambda w, c: c.post(f"{w['base']}/yearclocks", json={"name": "Matrix clock"}), {"owner", "admin"}),
    ("list Yearclock grants", lambda w, c: c.get(f"{w['base']}/yearclocks/{w['clock']['id']}/access"), {"owner", "admin"}),
    ("list people", lambda w, c: c.get(f"{w['base']}/memberships"), {"owner", "admin"}),
    ("list Labels", lambda w, c: c.get(f"{w['base']}/labels"), {"owner", "admin", "editor", "viewer", "member"}),
    ("create Label", lambda w, c: c.post(f"{w['base']}/labels", json={"name": "Matrix", "color": "#1f5f99"}), {"owner", "admin", "editor"}),
    ("list Organization Categories", lambda w, c: c.get(f"{w['base']}/categories"), {"owner", "admin", "editor", "viewer", "member"}),
    ("create Organization Category", lambda w, c: c.post(f"{w['base']}/categories", json={"name": "Matrix", "color": "#1f5f99"}), {"owner", "admin"}),
    # Stale versions or missing confirmations make allowed calls answer 409, so the matrix never changes state.
    ("rename Label", lambda w, c: c.patch(f"{w['base']}/labels/{w['label']['id']}", json={"name": "Renamed", "color": "#1f5f99", "expected_version": 999}), {"owner", "admin"}),
    ("merge Label", lambda w, c: c.post(f"{w['base']}/labels/{w['label']['id']}/merge", json={"into_label_id": w["other_label"]["id"], "expected_version": 1}), {"owner", "admin"}),
    ("delete Label", lambda w, c: c.delete(f"{w['base']}/labels/{w['label']['id']}?expected_version=1"), {"owner", "admin"}),
    ("change Organization Category", lambda w, c: c.patch(f"{w['base']}/categories/{w['org_category']['id']}", json={"name": "Renamed", "color": "#1f5f99", "expected_version": 999}), {"owner", "admin"}),
    ("delete Organization Category", lambda w, c: c.delete(f"{w['base']}/categories/{w['org_category']['id']}?expected_version=1"), {"owner", "admin"}),
    ("change Organization Category from a Yearclock", lambda w, c: c.patch(f"{w['base']}/yearclocks/{w['clock']['id']}/categories/{w['org_category']['id']}", json={"name": "Renamed", "color": "#1f5f99", "expected_version": 1}), set()),
    ("record a Yearclock visit", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/visit"), {"owner", "admin", "editor", "viewer"}),
    ("change Yearclock layout", lambda w, c: c.patch(f"{w['base']}/yearclocks/{w['clock']['id']}/layout", json={"start_month": 8, "expected_version": 999}), {"owner", "admin", "editor"}),
    ("change Lane appearance", lambda w, c: c.patch(f"{w['base']}/yearclocks/{w['clock']['id']}/lanes/{w['clock']['lanes'][0]['id']}", json={"name": "General", "height": "tall", "expected_version": 999}), {"owner", "admin", "editor"}),
    ("bulk edit Events", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/events/bulk", json={"items": [{"id": w["event"]["id"], "expected_version": 999}], "action": "delete"}), {"owner", "admin", "editor"}),
    ("preview Plan Again", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/plan-again", json={"season_start": "2026-01-01", "lane_ids": [w["clock"]["lanes"][0]["id"]], "dry_run": True}), {"owner", "admin", "editor"}),
    ("copy a Lane from another Yearclock", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/lanes/copy", json={"source_lane_id": w["source_clock"]["lanes"][0]["id"], "include_events": False}), {"owner", "admin", "editor"}),
    ("link a Lane from another Yearclock", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/lanes/link", json={"source_lane_id": w["source_clock"]["lanes"][0]["id"]}), {"owner", "admin", "editor"}),
    ("read Event history", lambda w, c: c.get(f"{w['base']}/yearclocks/{w['clock']['id']}/events/{w['event']['id']}/history"), {"owner", "admin", "editor", "viewer"}),
    ("preview a version restore", lambda w, c: c.get(f"{w['base']}/yearclocks/{w['clock']['id']}/events/{w['event']['id']}/history/{w['revision']['id']}/restore-preview"), {"owner", "admin", "editor"}),
    ("restore an earlier version", lambda w, c: c.post(f"{w['base']}/yearclocks/{w['clock']['id']}/events/{w['event']['id']}/history/{w['revision']['id']}/restore", json={"expected_version": 999}), {"owner", "admin", "editor"}),
    ("read changes since a time", lambda w, c: c.get(f"{w['base']}/yearclocks/{w['clock']['id']}/changes", params={"since": "2026-01-01T00:00:00Z", "limit": 1}), {"owner", "admin", "editor", "viewer"}),
    ("list Groups", lambda w, c: c.get(f"{w['base']}/groups"), {"owner", "admin"}),
    ("create a Group", lambda w, c: c.post(f"{w['base']}/groups", json={"name": "Matrix group"}), {"owner", "admin"}),
    ("rename a Group", lambda w, c: c.patch(f"{w['base']}/groups/{w['group']['id']}", json={"name": "Matrix renamed", "expected_version": 999}), {"owner", "admin"}),
    ("read own Groups", lambda w, c: c.get(f"{w['base']}/me/groups"), {"owner", "admin", "editor", "viewer", "member"}),
    ("list Group access to a Yearclock", lambda w, c: c.get(f"{w['base']}/yearclocks/{w['clock']['id']}/group-access"), {"owner", "admin"}),
    ("grant a Group access", lambda w, c: c.put(f"{w['base']}/yearclocks/{w['source_clock']['id']}/group-access", json={"group_id": w["group"]["id"], "role": "viewer"}), {"owner", "admin"}),
    ("share with the whole Organization", lambda w, c: c.put(f"{w['base']}/yearclocks/{w['clock']['id']}/organization-access", json={"role": "viewer", "expected_version": 999}), {"owner", "admin"}),
    ("preview bulk invitations", lambda w, c: c.post(f"{w['base']}/invitations/bulk", json={"emails": ["matrix-bulk@example.com"], "role": "member"}), {"owner", "admin"}),
    ("read a person's access", lambda w, c: c.get(f"{w['base']}/access-overview/people/{w['memberships']['viewer']['id']}"), {"owner", "admin"}),
    ("read who has access to a Yearclock", lambda w, c: c.get(f"{w['base']}/yearclocks/{w['clock']['id']}".replace("/yearclocks/", "/access-overview/yearclocks/")), {"owner", "admin"}),
    ("invite Member", lambda w, c: c.post(f"{w['base']}/invitations", json={"email": "matrix-invitee@example.com", "role": "member"}), {"owner", "admin"}),
    ("list own notifications", lambda w, c: c.get(f"{w['base']}/notifications"), {"owner", "admin", "editor", "viewer", "member"}),
    ("count unread notifications", lambda w, c: c.get(f"{w['base']}/notifications/unread-count"), {"owner", "admin", "editor", "viewer", "member"}),
    ("mark own notifications read", lambda w, c: c.post(f"{w['base']}/notifications/read-all"), {"owner", "admin", "editor", "viewer", "member"}),
    ("read notification settings", lambda w, c: c.get(f"{w['base']}/notification-settings"), {"owner", "admin", "editor", "viewer", "member"}),
    ("change notification settings", lambda w, c: c.put(f"{w['base']}/notification-settings", json={"settings": {"role_changed": {"in_app": True, "email": False}}}), {"owner", "admin", "editor", "viewer", "member"}),
    ("read activity", lambda w, c: c.get(f"{w['base']}/audit-events"), {"owner", "admin"}),
    ("list Support Access", lambda w, c: c.get(f"{w['base']}/support-access"), {"owner", "admin"}),
    ("read seats", lambda w, c: c.get(f"{w['base']}/billing/seats"), {"owner"}),
    ("preview seat increase", lambda w, c: c.post(f"{w['base']}/billing/seats/increase-preview", json={"target_seats": 7, "expected_version": 1}), {"owner"}),
    ("cancel the subscription", lambda w, c: c.post(f"{w['base']}/billing/cancel", json={"reason": "other"}), {"owner"}),
    ("undo the cancellation", lambda w, c: c.post(f"{w['base']}/billing/cancel/undo"), {"owner"}),
    ("subscribe again", lambda w, c: c.post(f"{w['base']}/billing/resubscribe", json={"seats": 3}), {"owner"}),
    ("transfer ownership", lambda w, c: c.post(f"{w['base']}/memberships/{w['memberships']['member']['id']}/transfer-ownership", json={"expected_version": 999, "keep_owner": False}), {"owner"}),
    ("read the billing contact", lambda w, c: c.get(f"{w['base']}/billing/contact"), {"owner"}),
    ("change the billing contact", lambda w, c: c.put(f"{w['base']}/billing/contact", json={"billing_name": "Northwind", "billing_email": "billing@example.com"}), {"owner"}),
    ("open billing portal", lambda w, c: c.post(f"{w['base']}/billing/portal"), {"owner"}),
    ("download the Organization Export", lambda w, c: c.get(f"{w['base']}/export"), {"owner"}),
    ("check deletion", lambda w, c: c.get(f"{w['base']}/deletion"), {"owner"}),
    ("platform health", lambda w, c: c.get("/api/v1/platform/health"), {"platform_admin", "support_agent"}),
    ("platform Organizations", lambda w, c: c.get("/api/v1/platform/organizations"), {"platform_admin"}),
    ("request Support Access", lambda w, c: c.post("/api/v1/platform/support-access", json={"organization_id": w["organization_id"], "case_reference": "MATRIX"}), {"support_agent"}),
]


@pytest.mark.parametrize(("name", "call", "allowed"), CASES, ids=[case[0] for case in CASES])
def test_authorization_matrix(world, name, call, allowed) -> None:
    outcomes = {}
    for actor in ACTORS:
        response = call(world, world["clients"][actor])
        outcomes[actor] = ALLOWED if response.status_code < 400 or response.status_code == 409 else DENIED
        if outcomes[actor] == DENIED:
            assert response.status_code in {401, 403, 404}, (name, actor, response.status_code, response.text)
    assert {actor for actor, outcome in outcomes.items() if outcome == ALLOWED} == allowed, (name, outcomes)


@pytest.mark.parametrize("actor", ["member", "editor", "viewer"])
def test_members_cannot_promote_themselves_or_others(world, actor) -> None:
    client = world["clients"][actor]
    own = world["memberships"][actor]
    for role in ("admin", "owner"):
        response = client.patch(f"{world['base']}/memberships/{own['id']}", json={"role": role, "expected_version": own["version"]})
        assert response.status_code == 403, (actor, role, response.text)
    other = world["memberships"]["member" if actor != "member" else "viewer"]
    assert client.patch(f"{world['base']}/memberships/{other['id']}", json={"role": "admin", "expected_version": other["version"]}).status_code == 403
    grant = client.put(f"{world['base']}/yearclocks/{world['clock']['id']}/access", json={"user_account_id": own["user_account_id"], "role": "editor"})
    assert grant.status_code == 403
    assert world["memberships"][actor]["role"] == "member"
    fresh = world["clients"]["owner"].get(f"{world['base']}/memberships").json()
    assert next(item for item in fresh if item["id"] == own["id"])["role"] == "member"


def test_admins_cannot_promote_themselves_or_anyone_to_owner(world) -> None:
    client = world["clients"]["admin"]
    own = world["memberships"]["admin"]
    assert client.patch(f"{world['base']}/memberships/{own['id']}", json={"role": "owner", "expected_version": own["version"]}).status_code == 403
    member = world["memberships"]["member"]
    assert client.patch(f"{world['base']}/memberships/{member['id']}", json={"role": "owner", "expected_version": member["version"]}).status_code == 403
    owner = world["memberships"]["owner"]
    assert client.patch(f"{world['base']}/memberships/{owner['id']}", json={"role": "member", "expected_version": owner["version"]}).status_code == 403


def test_viewer_and_ungranted_member_cannot_touch_another_organizations_or_hidden_content(world) -> None:
    event = world["event"]
    body = {**_event_body(world, "Tampered"), "expected_version": event["version"]}
    for actor in ("viewer", "member", "stranger"):
        response = world["clients"][actor].patch(f"{world['base']}/yearclocks/{world['clock']['id']}/events/{event['id']}", json=body)
        assert response.status_code in {403, 404}, (actor, response.status_code)
    stranger_base = f"/api/v1/organizations/{world['stranger_org']}"
    assert world["clients"]["owner"].get(stranger_base).status_code == 404
    assert world["clients"]["owner"].get(f"{stranger_base}/memberships").status_code in {403, 404}


def test_rls_hides_every_tenant_table_across_organizations(world) -> None:
    session_factory = create_session_factory(world["engine"])
    tables = ("yearclocks", "lanes", "categories", "events", "event_series", "series_occurrences", "yearclock_access_grants", "organization_memberships", "organization_invitations", "audit_events", "support_access_requests", "labels", "yearclock_visits", "event_revisions", "member_groups", "member_group_members", "yearclock_group_grants", "invitation_groups")
    with transaction_session(session_factory, RequestContext(organization_id=world["stranger_org"])) as session:
        foreign = {table: session.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id = :id"), {"id": world["organization_id"]}).scalar_one() for table in tables}
    with transaction_session(session_factory, RequestContext()) as session:
        anonymous = {table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in tables if table not in {"organization_memberships", "organization_invitations"}}
    assert set(foreign.values()) == {0}, foreign
    assert set(anonymous.values()) == {0}, anonymous
