"""Bulk invitations and invitation Groups (Shadow V2, P10a ticket 05)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, invitation_token, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _world(stack, database_url, subject, seats):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=seats)
    return application, owner, organization_id, f"/api/v1/organizations/{organization_id}"


def test_the_preview_skips_what_cannot_be_invited_and_counts_seats(database_url, stack) -> None:
    application, owner, organization_id, base = _world(stack, database_url, "bulk-invite-owner", seats=3)
    join(application, owner, organization_id, subject="bulk-existing", email="existing@example.com")
    owner.post(f"{base}/invitations", json={"email": "pending@example.com"})
    emails = ["Ann@Example.com", "not-an-address", "ann@example.com", "existing@example.com", "pending@example.com", "ben@example.com", "cat@example.com"]
    preview = owner.post(f"{base}/invitations/bulk", json={"emails": emails, "role": "member"})
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "invite": ["ann@example.com", "ben@example.com", "cat@example.com"],
        "skipped": [{"email": "not-an-address", "reason": "invalid"}, {"email": "ann@example.com", "reason": "duplicate"}, {"email": "existing@example.com", "reason": "member"}, {"email": "pending@example.com", "reason": "invited"}],
        "seats_needed": 3,
        "created": 0,
    }
    refused = owner.post(f"{base}/invitations/bulk", json={"emails": emails, "role": "member", "dry_run": False})
    assert refused.status_code == 409 and refused.json()["detail"] == {"reason": "seats_needed", "seats_needed": 3}
    assert [item["email"] for item in owner.get(f"{base}/invitations").json() if item["status"] == "pending"] == ["pending@example.com"]
    assert owner.post(f"{base}/invitations/bulk", json={"emails": [f"p{index}@example.com" for index in range(51)]}).status_code == 422


