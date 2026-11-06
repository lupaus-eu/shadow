"""The notification inbox and access notifications (Yearclock V2, P8 ticket 02)."""
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from app.models import BackgroundJob
from app.notifications import CLEANUP_JOB, cleanup_notifications
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


class World:
    def __init__(self, stack, database_url, subject, stripe=None):
        verifier = Verifier()
        self.stripe = stripe or Stripe()
        self.application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=self.stripe, stripe_webhook_verifier=verifier, clock=lambda: NOW)
        self.stack = stack
        self.verifier = verifier
        self.owner = stack.enter_context(TestClient(self.application))
        login(self.owner)
        self.organization_id = active_org(self.owner, verifier, seats=6)
        self.org = f"/api/v1/organizations/{self.organization_id}"
        self.clock = self.owner.get(self.org).json()["yearclocks"][0]
        self.base = f"{self.org}/yearclocks/{self.clock['id']}"
        self.subject = subject

    def person(self, name, role="member"):
        application, user_id = join(self.application, self.owner, self.organization_id, subject=f"{self.subject}-{name}", email=f"{self.subject}-{name}@example.com", role=role)
        client = self.stack.enter_context(TestClient(application))
        login(client)
        membership = next(item for item in self.owner.get(f"{self.org}/memberships").json() if item["user_account_id"] == user_id)
        return client, user_id, membership

    def notices(self, client, type=None):
        items = client.get(f"{self.org}/notifications").json()["items"]
        return [item for item in items if type is None or item["type"] == type]

    def unread(self, client):
        return client.get(f"{self.org}/notifications/unread-count").json()["unread"]

    def grant(self, user_id, role, **extra):
        response = self.owner.put(f"{self.base}/access", json={"user_account_id": user_id, "role": role, **extra})
        assert response.status_code == 200, response.text
        return response.json()


def test_a_grant_notifies_the_person_and_a_newer_unread_one_replaces_it(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-grant")
    member, user_id, _ = world.person("member")
    assert world.notices(member) == []
    grant = world.grant(user_id, "viewer")
    [notice] = world.notices(member)
    assert notice["type"] == "access_changed" and notice["read_at"] is None
    assert notice["params"] == {"yearclock_id": world.clock["id"], "yearclock_name": world.clock["name"], "from_role": "none", "to_role": "viewer"}
    world.grant(user_id, "editor", expected_version=grant["version"])
    [notice] = world.notices(member)
    assert notice["params"]["from_role"] == "none" and notice["params"]["to_role"] == "editor" and world.unread(member) == 1
    assert world.notices(world.owner, "access_changed") == []


def test_a_change_that_ends_where_it_began_leaves_no_notice(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-undo")
    member, user_id, _ = world.person("member")
    grant = world.grant(user_id, "viewer")
    world.notices(member)
    assert member.post(f"{world.org}/notifications/read-all").json() == {"updated": 1}
    removed = world.owner.delete(f"{world.base}/access/{user_id}", params={"expected_version": grant["version"]})
    assert removed.status_code == 204
    notice = world.notices(member)[0]
    assert notice["read_at"] is None and notice["params"]["from_role"] == "viewer" and notice["params"]["to_role"] == "none"
    # Granting again before the person read the removal: the unread notice cancels out, the read one stays.
    again = world.grant(user_id, "viewer")
    assert world.unread(member) == 0 and len(world.notices(member)) == 1
    assert world.owner.delete(f"{world.base}/access/{user_id}", params={"expected_version": again["version"]}).status_code == 204
    assert world.unread(member) == 1 and world.notices(member)[0]["params"]["to_role"] == "none"


def test_only_people_whose_effective_role_changed_are_notified(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-group")
    first, first_id, first_membership = world.person("first")
    second, second_id, second_membership = world.person("second")
    world.grant(first_id, "editor")
    group = world.owner.post(f"{world.org}/groups", json={"name": "Planners"}).json()
    for membership in (first_membership, second_membership):
        assert world.owner.put(f"{world.org}/groups/{group['id']}/members/{membership['id']}").status_code == 200
    assert world.unread(first) == 1 and world.unread(second) == 0
    assert world.owner.put(f"{world.base}/group-access", json={"group_id": group["id"], "role": "viewer"}).status_code == 200
    assert world.unread(first) == 1  # already an Editor: nothing changed for them
    [notice] = world.notices(second)
    assert notice["params"]["from_role"] == "none" and notice["params"]["to_role"] == "viewer"
    # Removing a member from the Group takes their access back, which cancels the unread notice; the one with the direct grant keeps theirs.
    assert world.owner.delete(f"{world.org}/groups/{group['id']}/members/{second_membership['id']}").status_code == 200
    assert world.notices(second) == []
    assert world.owner.delete(f"{world.org}/groups/{group['id']}/members/{first_membership['id']}").status_code == 200
    assert world.unread(first) == 1


def test_sharing_with_the_whole_organization_notifies_each_member_but_not_managers(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-wide")
    member, _, _ = world.person("member")
    admin, _, _ = world.person("admin", role="admin")
    version = world.owner.get(world.org).json()["yearclocks"][0]["version"]
    response = world.owner.put(f"{world.base}/organization-access", json={"role": "viewer", "expected_version": version})
    assert response.status_code == 200, response.text
    assert [item["params"]["to_role"] for item in world.notices(member)] == ["viewer"]
    assert world.notices(admin, "access_changed") == [] and world.notices(world.owner, "access_changed") == []


def test_notifications_carry_no_event_content(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-content")
    member, user_id, _ = world.person("member")
    lane = world.clock["lanes"][0]["id"]
    assert world.owner.post(f"{world.base}/events", json={"title": "Secret reorganisation", "lane_id": lane, "starts_on": "2026-10-01", "description": "Confidential"}).status_code == 201
    world.grant(user_id, "viewer")
    assert "Secret" not in str(world.notices(member)) and "Confidential" not in str(world.notices(member))


def test_people_read_and_mark_only_their_own_notifications(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-own")
    first, first_id, _ = world.person("first")
    second, second_id, _ = world.person("second")
    world.grant(first_id, "viewer")
    world.grant(second_id, "viewer")
    [mine] = world.notices(first)
    assert world.notices(world.owner, "access_changed") == [] and len(world.notices(second)) == 1
    assert second.post(f"{world.org}/notifications/{mine['id']}/read").status_code == 404
    assert world.owner.post(f"{world.org}/notifications/{mine['id']}/read").status_code == 404
    assert first.post(f"{world.org}/notifications/{mine['id']}/read").status_code == 204
    assert world.unread(first) == 0 and world.unread(second) == 1
    assert world.notices(first)[0]["read_at"] is not None
    assert world.owner.post(f"{world.org}/notifications/read-all").status_code == 200
    assert world.unread(second) == 1


def test_a_stranger_cannot_open_the_inbox_of_another_organization(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-stranger")
    other = World(stack, database_url, "ntf-stranger-other")
    assert other.owner.get(f"{world.org}/notifications").status_code == 404
    assert other.owner.get(f"{world.org}/notifications/unread-count").status_code == 404
    assert other.owner.post(f"{world.org}/notifications/read-all").status_code == 404


def test_the_list_is_paged_newest_first(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-page")
    member, user_id, _ = world.person("member")
    clocks = [world.clock["id"]]
    for number in range(24):
        clocks.append(world.owner.post(f"{world.org}/yearclocks", json={"name": f"Clock {number}"}).json()["id"])
        assert world.owner.put(f"{world.org}/yearclocks/{clocks[-1]}/access", json={"user_account_id": user_id, "role": "viewer"}).status_code == 200
    first = member.get(f"{world.org}/notifications").json()
    assert len(first["items"]) == 20 and first["next_cursor"]
    assert first["items"][0]["params"]["yearclock_name"] == "Clock 23"
    second = member.get(f"{world.org}/notifications", params={"cursor": first["next_cursor"]}).json()
    assert len(second["items"]) == 4 and second["next_cursor"] is None
    assert {item["id"] for item in first["items"]}.isdisjoint(item["id"] for item in second["items"])
    assert member.get(f"{world.org}/notifications", params={"cursor": "nonsense"}).status_code == 422
    assert len(member.get(f"{world.org}/notifications", params={"unread": "true"}).json()["items"]) == 20


def test_role_changes_and_accepted_invitations_notify(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-roles")
    member, user_id, membership = world.person("member")
    # The owner invited the member, who accepted.
    [accepted] = world.notices(world.owner)
    assert accepted["type"] == "invitation_accepted" and accepted["params"]["role"] == "member" and accepted["params"]["name"]
    assert world.owner.patch(f"{world.org}/memberships/{membership['id']}", json={"role": "admin", "expected_version": membership["version"]}).status_code == 200
    [change] = world.notices(member)
    assert change["type"] == "role_changed" and change["params"] == {"from_role": "member", "to_role": "admin"}
    # Giving ownership tells the other Owners as well as the person.
    second_owner, _, second_membership = world.person("second", role="admin")
    other = world.owner.get(f"{world.org}/memberships").json()
    version = next(item["version"] for item in other if item["id"] == second_membership["id"])
    assert world.owner.patch(f"{world.org}/memberships/{second_membership['id']}", json={"role": "owner", "expected_version": version}).status_code == 200
    assert "role_changed" in [item["type"] for item in world.notices(second_owner)]
    assert world.notices(world.owner, "ownership_changed") == []  # the actor is not told of their own action
    assert world.notices(world.person("third", role="admin")[0], "ownership_changed") == []


def test_cleanup_deletes_notifications_older_than_the_retention(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-cleanup")
    member, user_id, _ = world.person("member")
    world.grant(user_id, "viewer")
    engine = world.application.state.database_engine
    old = uuid4()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO notifications (id, organization_id, recipient_user_id, type, params, created_at) VALUES (:id, :org, :user, 'access_changed', '{}', now() - interval '91 days')"), {"id": old, "org": world.organization_id, "user": user_id})
        connection.execute(text("INSERT INTO notifications (id, organization_id, recipient_user_id, type, params, created_at) VALUES (:id, :org, :user, 'access_changed', '{}', now() - interval '89 days')"), {"id": uuid4(), "org": world.organization_id, "user": user_id})
    assert len(world.notices(member)) == 3
    from app.database import RequestContext, transaction_session
    with transaction_session(world.application.state.session_factory, RequestContext(organization_id=UUID(world.organization_id))) as session:
        job = BackgroundJob(id=uuid4(), organization_id=UUID(world.organization_id), job_type=CLEANUP_JOB, payload={}, idempotency_key=str(uuid4()))
        cleanup_notifications(session, job, datetime.now(UTC))
    assert len(world.notices(member)) == 2
    assert str(old) not in {item["id"] for item in world.notices(member)}
