"""Organization Labels (Yearclock V2, P2 ticket 02)."""
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import RequestContext, create_session_factory, transaction_session
from app.label_routes import LABEL_COLORS
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login

BLUE, GREEN = LABEL_COLORS[0], LABEL_COLORS[1]


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _organization(stack, database_url, subject, *, seats=5):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=seats)
    return application, owner, organization_id, f"/api/v1/organizations/{organization_id}"


def _member(stack, application, owner, organization_id, name, role="member"):
    member_app, user_id = join(application, owner, organization_id, subject=f"labels-{name}", email=f"labels-{name}@example.com", role=role)
    client = stack.enter_context(TestClient(member_app))
    login(client)
    return client, user_id


def test_owners_curate_labels_and_every_change_is_audited(database_url, stack) -> None:
    _, owner, _, base = _organization(stack, database_url, "labels-owner")
    created = owner.post(f"{base}/labels", json={"name": "  Decision   needed ", "color": BLUE.upper()})
    assert created.status_code == 201 and created.json()["name"] == "Decision needed" and created.json()["color"] == BLUE
    again = owner.post(f"{base}/labels", json={"name": "decision NEEDED", "color": GREEN})
    assert again.status_code == 200 and again.json()["id"] == created.json()["id"]
    label = created.json()
    renamed = owner.patch(f"{base}/labels/{label['id']}", json={"name": "Needs decision", "color": GREEN, "expected_version": 1})
    stale = owner.patch(f"{base}/labels/{label['id']}", json={"name": "Other", "color": GREEN, "expected_version": 1})
    other = owner.post(f"{base}/labels", json={"name": "Finance", "color": BLUE}).json()
    duplicate = owner.patch(f"{base}/labels/{other['id']}", json={"name": "needs decision", "color": BLUE, "expected_version": 1})
    assert renamed.status_code == 200 and renamed.json()["version"] == 2
    assert stale.status_code == 409 and stale.json()["detail"] == {"latest_version": 2}
    assert duplicate.status_code == 409 and duplicate.json()["detail"]["reason"] == "duplicate_name"
    assert owner.post(f"{base}/labels", json={"name": "Bad", "color": "#123456"}).status_code == 422
    assert owner.post(f"{base}/labels", json={"name": "x" * 61, "color": BLUE}).status_code == 422
    assert [item["name"] for item in owner.get(f"{base}/labels").json()] == ["Finance", "Needs decision"]

    unconfirmed = owner.post(f"{base}/labels/{label['id']}/merge", json={"into_label_id": other["id"], "expected_version": 2})
    assert unconfirmed.status_code == 409 and unconfirmed.json()["detail"] == {"reason": "confirmation_required", "usage": 0}
    assert len(owner.get(f"{base}/labels").json()) == 2
    merged = owner.post(f"{base}/labels/{label['id']}/merge", json={"into_label_id": other["id"], "expected_version": 2, "confirm": True})
    assert merged.status_code == 200 and merged.json()["id"] == other["id"]
    assert owner.post(f"{base}/labels/{other['id']}/merge", json={"into_label_id": other["id"], "expected_version": 2, "confirm": True}).status_code == 422

    refused = owner.delete(f"{base}/labels/{other['id']}?expected_version=2")
    deleted = owner.delete(f"{base}/labels/{other['id']}?expected_version=2&confirm=true")
    assert refused.status_code == 409 and refused.json()["detail"]["usage"] == 0
    assert deleted.status_code == 204 and owner.get(f"{base}/labels").json() == []

    actions = [item["action"] for item in owner.get(f"{base}/audit-events", params={"prefix": "label"}).json()["items"]]
    assert sorted(actions) == sorted(["label.created", "label.created", "label.updated", "label.merged", "label.deleted"])
    merged_event = next(item for item in owner.get(f"{base}/audit-events", params={"prefix": "label"}).json()["items"] if item["action"] == "label.merged")
    assert merged_event["change_summary"] == {"from": "Needs decision", "into": "Finance", "affected_events": 0}


def test_only_owners_and_admins_manage_while_editors_may_create(database_url, stack) -> None:
    application, owner, organization_id, base = _organization(stack, database_url, "labels-roles-owner")
    clock = owner.get(base).json()["yearclocks"][0]["id"]
    admin, _ = _member(stack, application, owner, organization_id, "admin", role="admin")
    editor, editor_id = _member(stack, application, owner, organization_id, "editor")
    viewer, viewer_id = _member(stack, application, owner, organization_id, "viewer")
    member, _ = _member(stack, application, owner, organization_id, "plain")
    owner.put(f"{base}/yearclocks/{clock}/access", json={"user_account_id": editor_id, "role": "editor"})
    owner.put(f"{base}/yearclocks/{clock}/access", json={"user_account_id": viewer_id, "role": "viewer"})

    by_admin = admin.post(f"{base}/labels", json={"name": "Board", "color": BLUE})
    by_editor = editor.post(f"{base}/labels", json={"name": "Budget", "color": GREEN})
    assert by_admin.status_code == 201 and by_editor.status_code == 201
    assert viewer.post(f"{base}/labels", json={"name": "Nope", "color": BLUE}).status_code == 403
    assert member.post(f"{base}/labels", json={"name": "Nope", "color": BLUE}).status_code == 403
    label = by_editor.json()
    for client in (editor, viewer, member):
        assert client.patch(f"{base}/labels/{label['id']}", json={"name": "Changed", "color": BLUE, "expected_version": 1}).status_code == 403
        assert client.delete(f"{base}/labels/{label['id']}?expected_version=1&confirm=true").status_code == 403
        assert client.post(f"{base}/labels/{label['id']}/merge", json={"into_label_id": by_admin.json()["id"], "expected_version": 1, "confirm": True}).status_code == 403
        assert [item["name"] for item in client.get(f"{base}/labels").json()] == ["Board", "Budget"]
    assert admin.patch(f"{base}/labels/{label['id']}", json={"name": "Budget 2027", "color": BLUE, "expected_version": 1}).status_code == 200


def test_label_ceiling_read_only_state_and_tenant_isolation(database_url, stack, monkeypatch) -> None:
    application, owner, organization_id, base = _organization(stack, database_url, "labels-limits-owner")
    monkeypatch.setenv("LIMIT_LABELS_PER_ORGANIZATION", "2")
    owner.post(f"{base}/labels", json={"name": "One", "color": BLUE})
    owner.post(f"{base}/labels", json={"name": "Two", "color": BLUE})
    third = owner.post(f"{base}/labels", json={"name": "Three", "color": BLUE})
    assert third.status_code == 409 and third.json()["detail"] == {"reason": "limit_reached", "limit": "labels_per_organization", "maximum": 2}
    assert owner.post(f"{base}/labels", json={"name": "one", "color": BLUE}).status_code == 200

    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    label = owner.get(f"{base}/labels").json()[0]
    assert owner.post(f"{base}/labels", json={"name": "Fresh", "color": BLUE}).status_code == 403
    assert owner.patch(f"{base}/labels/{label['id']}", json={"name": "Renamed", "color": BLUE, "expected_version": 1}).status_code == 403
    assert len(owner.get(f"{base}/labels").json()) == 2

    session_factory = create_session_factory(application.state.database_engine)
    with transaction_session(session_factory, RequestContext(organization_id=uuid4())) as session:
        foreign = session.execute(text("SELECT count(*) FROM labels WHERE organization_id = :id"), {"id": organization_id}).scalar_one()
    stranger_verifier = Verifier()
    stranger = stack.enter_context(TestClient(create_app(database_url=database_url, oidc_client=OIDC("labels-stranger", "labels-stranger@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=stranger_verifier, clock=lambda: NOW)))
    login(stranger)
    active_org(stranger, stranger_verifier)
    assert foreign == 0
    assert stranger.get(f"{base}/labels").status_code == 404
