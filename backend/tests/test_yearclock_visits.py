"""Recently opened Yearclocks (Yearclock V2, P2 ticket 01)."""
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import RequestContext, create_session_factory, transaction_session
from app.jobs import run_one_background_job, schedule_organization_purge_jobs
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _organization(stack, database_url, subject):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=4)
    base = f"/api/v1/organizations/{organization_id}"
    first = owner.get(base).json()["yearclocks"][0]["id"]
    clocks = [first] + [owner.post(f"{base}/yearclocks", json={"name": f"Clock {index}"}).json()["id"] for index in range(6)]
    return application, owner, organization_id, base, clocks


def _visit(client, base, yearclock_id):
    return client.post(f"{base}/yearclocks/{yearclock_id}/visit")


def test_the_recent_list_keeps_the_five_latest_visits_newest_first(database_url, stack) -> None:
    _, owner, _, base, clocks = _organization(stack, database_url, "recent-owner")
    assert owner.get(base).json()["recent_yearclock_ids"] == []
    for yearclock_id in clocks:
        assert _visit(owner, base, yearclock_id).status_code == 200
    assert _visit(owner, base, clocks[1]).status_code == 200
    recent = owner.get(base).json()["recent_yearclock_ids"]
    assert recent == [clocks[1], clocks[6], clocks[5], clocks[4], clocks[3]]


def test_visits_are_private_and_follow_access(database_url, stack) -> None:
    application, owner, organization_id, base, clocks = _organization(stack, database_url, "private-recent-owner")
    member_app, member_id = join(application, owner, organization_id, subject="private-recent-member", email="private-recent-member@example.com")
    owner.put(f"{base}/yearclocks/{clocks[0]}/access", json={"user_account_id": member_id, "role": "viewer"})
    _visit(owner, base, clocks[2])
    with TestClient(member_app) as member:
        login(member)
        hidden = _visit(member, base, clocks[2]).status_code
        assert _visit(member, base, clocks[0]).status_code == 200
        member_recent = member.get(base).json()["recent_yearclock_ids"]
        grant = next(item for item in owner.get(f"{base}/yearclocks/{clocks[0]}/access").json() if item["user_account_id"] == member_id)
        assert owner.delete(f"{base}/yearclocks/{clocks[0]}/access/{member_id}?expected_version={grant['version']}").status_code == 204
        after_revoke = member.get(base).json()["recent_yearclock_ids"]
    assert grant["role"] == "viewer"
    assert hidden == 404 and member_recent == [clocks[0]] and after_revoke == []
    assert owner.get(base).json()["recent_yearclock_ids"] == [clocks[2]]

    session_factory = create_session_factory(application.state.database_engine)
    with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
        without_user = session.execute(text("SELECT count(*) FROM yearclock_visits")).scalar_one()
    assert without_user == 0


def test_deleted_yearclocks_leave_the_list_and_removal_or_purge_drops_visits(database_url, stack) -> None:
    application, owner, organization_id, base, clocks = _organization(stack, database_url, "cleanup-recent-owner")
    member_app, _ = join(application, owner, organization_id, subject="cleanup-recent-member", email="cleanup-recent-member@example.com", role="admin")
    with TestClient(member_app) as member:
        login(member)
        _visit(member, base, clocks[3])
    _visit(owner, base, clocks[3])
    _visit(owner, base, clocks[4])
    version = next(item for item in owner.get(f"{base}/yearclocks").json() if item["id"] == clocks[4])["version"]
    assert owner.delete(f"{base}/yearclocks/{clocks[4]}?expected_version={version}").status_code == 204
    assert owner.get(base).json()["recent_yearclock_ids"] == [clocks[3]]

    membership = next(item for item in owner.get(f"{base}/memberships").json() if item["email"] == "cleanup-recent-member@example.com")
    owner.delete(f"{base}/memberships/{membership['id']}?expected_version={membership['version']}")
    with application.state.database_engine.connect() as connection:
        member_rows = connection.execute(text("SELECT count(*) FROM yearclock_visits WHERE membership_id = :id"), {"id": membership["id"]}).scalar_one()
    assert member_rows == 0

    owner.post(f"{base}/deletion", json={"confirm": True})
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET deletion_requested_at = now() - interval '31 days' WHERE id = :id"), {"id": organization_id})
    session_factory = create_session_factory(application.state.database_engine)
    schedule_organization_purge_jobs(session_factory, now=datetime.now(UTC) + timedelta(seconds=1))
    while run_one_background_job(session_factory, organization_id=organization_id):
        pass
    with application.state.database_engine.connect() as connection:
        remaining = connection.execute(text("SELECT count(*) FROM yearclock_visits WHERE organization_id = :id"), {"id": organization_id}).scalar_one()
    assert remaining == 0


def test_read_only_organizations_still_record_visits(database_url, stack) -> None:
    application, owner, organization_id, base, clocks = _organization(stack, database_url, "readonly-recent-owner")
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert _visit(owner, base, clocks[0]).status_code == 200
    assert owner.get(base).json()["recent_yearclock_ids"] == [clocks[0]]
