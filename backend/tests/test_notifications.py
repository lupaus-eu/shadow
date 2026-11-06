"""The notification inbox and access notifications (Shadow V2, P8 ticket 02)."""
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


def test_a_stranger_cannot_open_the_inbox_of_another_organization(database_url, stack) -> None:
    world = World(stack, database_url, "ntf-stranger")
    other = World(stack, database_url, "ntf-stranger-other")
    assert other.owner.get(f"{world.org}/notifications").status_code == 404
    assert other.owner.get(f"{world.org}/notifications/unread-count").status_code == 404
    assert other.owner.post(f"{world.org}/notifications/read-all").status_code == 404


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
    engine = world.application.state.database_engine
    old = uuid4()
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO notifications (id, organization_id, recipient_user_id, type, params, created_at) VALUES (:id, :org, :user, 'access_changed', '{}', now() - interval '91 days')"), {"id": old, "org": world.organization_id, "user": user_id})
        connection.execute(text("INSERT INTO notifications (id, organization_id, recipient_user_id, type, params, created_at) VALUES (:id, :org, :user, 'access_changed', '{}', now() - interval '89 days')"), {"id": uuid4(), "org": world.organization_id, "user": user_id})
    assert len(world.notices(member)) == 2
    from app.database import RequestContext, transaction_session
    with transaction_session(world.application.state.session_factory, RequestContext(organization_id=UUID(world.organization_id))) as session:
        job = BackgroundJob(id=uuid4(), organization_id=UUID(world.organization_id), job_type=CLEANUP_JOB, payload={}, idempotency_key=str(uuid4()))
        cleanup_notifications(session, job, datetime.now(UTC))
    assert len(world.notices(member)) == 1
    assert str(old) not in {item["id"] for item in world.notices(member)}
