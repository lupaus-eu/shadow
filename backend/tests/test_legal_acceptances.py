"""Acceptances of the required legal documents: the sign-up gate and the Owner's routes (ADR-0041)."""
from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.jobs import ORGANIZATION_PURGE_JOB, run_one_background_job, schedule_organization_purge_jobs
from app.database import create_session_factory
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, login
from test_notifications import World, stack  # noqa: F401 - the fixture
from test_organization_deletion import _age_request, _count, _organization
from test_platform_operations import _platform_app  # noqa: F401


def publish(application, key: str, version: int = 1) -> None:
    """Publish a document in the running application's library (both locales), as a release would."""
    library = application.state.legal_library
    for locale in ("fi", "en"):
        document = library._documents[(key, locale)]
        library._documents[(key, locale)] = replace(document, status="published", version=version)


def signup_body(**extra) -> dict:
    return {"organization_name": "Northwind", "time_zone": "Europe/Helsinki", "default_locale": "en", "billing_name": "Northwind", "billing_email": "billing@example.com", "initial_seats": 2, **extra}


def test_signup_needs_every_published_required_document_at_its_current_version(database_url, stack) -> None:
    application = create_app(database_url=database_url, oidc_client=OIDC("legal-signup", "legal-signup@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=Verifier(), clock=lambda: NOW)
    client = stack.enter_context(TestClient(application))
    login(client)
    # Nothing published yet: sign-up works as before.
    assert client.post("/api/v1/organization-signups", json=signup_body()).status_code == 201

    publish(application, "terms")
    publish(application, "dpa", version=3)
    refused = client.post("/api/v1/organization-signups", json=signup_body())
    assert refused.status_code == 422
    assert refused.json()["detail"] == {"reason": "legal_acceptance_required", "required": [{"document_key": "terms", "version": 1}, {"document_key": "dpa", "version": 3}]}
    stale = client.post("/api/v1/organization-signups", json=signup_body(accepted_documents=[{"document_key": "terms", "version": 1}, {"document_key": "dpa", "version": 2}]))
    assert stale.status_code == 422 and stale.json()["detail"]["required"] == [{"document_key": "dpa", "version": 3}]

    accepted = client.post("/api/v1/organization-signups", json=signup_body(default_locale="fi", accepted_documents=[{"document_key": "terms", "version": 1, "locale": "en"}, {"document_key": "dpa", "version": 3}, {"document_key": "privacy", "version": 1}]))
    assert accepted.status_code == 201, accepted.text
    with application.state.database_engine.connect() as connection:
        rows = connection.execute(text("SELECT document_key, version, locale, accepted_by_email FROM legal_acceptances WHERE organization_id = :id ORDER BY document_key"), {"id": accepted.json()["organization_id"]}).all()
    assert [tuple(row) for row in rows] == [("dpa", 3, "fi", "legal-signup@example.com"), ("terms", 1, "en", "legal-signup@example.com")]


def test_a_refused_signup_creates_nothing(database_url, stack) -> None:
    application = create_app(database_url=database_url, oidc_client=OIDC("legal-nothing", "legal-nothing@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=Verifier(), clock=lambda: NOW)
    client = stack.enter_context(TestClient(application))
    login(client)
    publish(application, "terms")
    assert client.post("/api/v1/organization-signups", json=signup_body(organization_name="Never created")).status_code == 422
    with application.state.database_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM organizations WHERE name = 'Never created'")).scalar_one() == 0


def test_an_owner_sees_and_records_acceptances_of_the_current_version_only(database_url, stack) -> None:
    world = World(stack, database_url, "legal-owner")
    publish(world.application, "terms")
    publish(world.application, "dpa")
    publish(world.application, "subprocessors")
    overview = world.owner.get(f"{world.org}/legal?locale=fi").json()["documents"]
    assert [(item["key"], item["state"]) for item in overview] == [("terms", "acceptance_due"), ("dpa", "acceptance_due"), ("subprocessors", "not_required")]
    assert overview[0]["title"] == "Palveluehdot" and overview[0]["accepted_version"] is None

    assert world.owner.post(f"{world.org}/legal/acceptances", json={"document_key": "terms", "version": 2}).status_code == 409
    assert world.owner.post(f"{world.org}/legal/acceptances", json={"document_key": "privacy", "version": 1}).status_code == 404
    assert world.owner.post(f"{world.org}/legal/acceptances", json={"document_key": "subprocessors", "version": 1}).status_code == 404
    first = world.owner.post(f"{world.org}/legal/acceptances", json={"document_key": "terms", "version": 1, "locale": "fi"}, headers={"X-Request-ID": "legal-accept-1"})
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "accepted" and first.json()["accepted_version"] == 1 and bool(first.json()["accepted_by_name"]) and not first.json()["accepted_by_former_member"]
    again = world.owner.post(f"{world.org}/legal/acceptances", json={"document_key": "terms", "version": 1})
    assert again.status_code == 200 and again.json()["accepted_at"] == first.json()["accepted_at"]

    with world.application.state.database_engine.connect() as connection:
        rows = connection.execute(text("SELECT locale, request_id FROM legal_acceptances WHERE organization_id = :id"), {"id": world.organization_id}).all()
        audits = connection.execute(text("SELECT change_summary FROM audit_events WHERE organization_id = :id AND action = 'organization.legal_accepted'"), {"id": world.organization_id}).scalars().all()
    assert [tuple(row) for row in rows] == [("fi", "legal-accept-1")]
    assert audits == [{"document_key": "terms", "version": 1}]

    publish(world.application, "terms", version=2)
    due = {item["key"]: item for item in world.owner.get(f"{world.org}/legal").json()["documents"]}
    assert due["terms"]["state"] == "acceptance_due" and due["terms"]["accepted_version"] == 1 and due["terms"]["current_version"] == 2
    assert world.owner.post(f"{world.org}/legal/acceptances", json={"document_key": "terms", "version": 1}).status_code == 409
    assert world.owner.post(f"{world.org}/legal/acceptances", json={"document_key": "terms", "version": 2}).json()["state"] == "accepted"


def test_only_owners_may_read_or_accept_and_other_organizations_are_hidden(database_url, stack) -> None:
    world = World(stack, database_url, "legal-roles")
    publish(world.application, "terms")
    admin, _, _ = world.person("admin", "admin")
    member, _, _ = world.person("member")
    for person in (admin, member):
        assert person.get(f"{world.org}/legal").status_code == 403
        assert person.post(f"{world.org}/legal/acceptances", json={"document_key": "terms", "version": 1}).status_code == 403
    stranger = World(stack, database_url, "legal-stranger")
    assert stranger.owner.get(f"{world.org}/legal").status_code == 404
    assert stranger.owner.post(f"{world.org}/legal/acceptances", json={"document_key": "terms", "version": 1}).status_code == 404
    assert world.owner.get(f"{world.org}/legal").status_code == 200


def test_the_acceptance_survives_the_organization_purge(database_url, stack) -> None:
    application, owner, organization_id, _ = _organization(stack, database_url, "legal-purge")
    publish(application, "terms")
    assert owner.post(f"/api/v1/organizations/{organization_id}/legal/acceptances", json={"document_key": "terms", "version": 1}).status_code == 200
    owner.post(f"/api/v1/organizations/{organization_id}/deletion", json={"confirm": True})
    session_factory = create_session_factory(application.state.database_engine)
    _age_request(application, organization_id, 31)
    schedule_organization_purge_jobs(session_factory, now=datetime.now(UTC))
    while run_one_background_job(session_factory, organization_id=organization_id):
        pass
    with application.state.database_engine.connect() as connection:
        status = connection.execute(text("SELECT status FROM organizations WHERE id = :id"), {"id": organization_id}).scalar_one()
    assert status == "purged"
    assert _count(application, "organization_memberships", organization_id) == 0
    assert _count(application, "legal_acceptances", organization_id) == 1
