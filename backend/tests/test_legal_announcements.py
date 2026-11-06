"""Announcing a published legal document version to Owners, once (ADR-0041)."""
from datetime import UTC, datetime

from sqlalchemy import text

from app.jobs import run_one_background_job
from app.database import create_session_factory
from app.legal_announcements import ANNOUNCE_JOB, schedule_legal_announcements
from test_legal_acceptances import publish
from test_notification_email import emails
from test_notifications import World, stack  # noqa: F401 - the fixture

NOW = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


def run_jobs(world) -> None:
    factory = create_session_factory(world.application.state.database_engine)
    while run_one_background_job(factory, organization_id=world.organization_id):
        pass


def schedule(world) -> int:
    factory = create_session_factory(world.application.state.database_engine)
    return schedule_legal_announcements(factory, world.application.state.legal_library, now=NOW)


def announced(world) -> list[tuple]:
    with world.application.state.database_engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text("SELECT document_key, version FROM legal_announcements ORDER BY document_key, version"))]


def mine(world, client) -> list[dict]:
    return world.notices(client, "legal_document_published")


def test_a_new_version_is_announced_once_to_the_owners_of_every_organization(database_url, stack) -> None:
    world = World(stack, database_url, "legal-announce")
    admin, _, _ = world.person("admin", "admin")
    publish(world.application, "terms")
    assert schedule(world) >= 1
    run_jobs(world)
    [notice] = mine(world, world.owner)
    assert notice["params"] == {"document_key": "terms", "version": 1, "effective_from": "2026-12-01", "acceptance": "required"}
    assert mine(world, admin) == []
    first = len(emails(world))

    # Running again, even after the jobs ran, sends nothing more.
    assert schedule(world) == 0
    run_jobs(world)
    assert len(mine(world, world.owner)) == 1 and len(emails(world)) == first
    assert ("terms", 1) in announced(world)

    publish(world.application, "terms", version=2)
    assert schedule(world) >= 1
    run_jobs(world)
    assert [item["params"]["version"] for item in mine(world, world.owner)] == [2, 1]


def test_an_organization_that_accepted_the_version_is_not_told(database_url, stack) -> None:
    world = World(stack, database_url, "legal-accepted")
    publish(world.application, "dpa")
    assert world.owner.post(f"{world.org}/legal/acceptances", json={"document_key": "dpa", "version": 1}).status_code == 200
    schedule(world)
    run_jobs(world)
    assert mine(world, world.owner) == []


def test_the_email_is_sent_even_when_the_person_turned_email_off_and_states_the_period(database_url, stack, monkeypatch) -> None:
    monkeypatch.setenv("LEGAL_CONTACT_EMAIL", "legal@shadow.example")
    world = World(stack, database_url, "legal-mandatory")
    owner_id = world.owner.get("/api/v1/auth/session").json()["user_account"]["id"]
    off = '{"legal": {"in_app": false, "email": false}}'
    with world.application.state.database_engine.begin() as connection:
        connection.execute(text("SELECT set_config('app.current_organization_id', :org, true), set_config('app.current_user_account_id', :user, true)"), {"org": world.organization_id, "user": owner_id})
        connection.execute(text("INSERT INTO notification_preferences (organization_id, user_id, settings) VALUES (:org, :user, CAST(:settings AS jsonb)) ON CONFLICT (organization_id, user_id) DO UPDATE SET settings = EXCLUDED.settings"), {"org": world.organization_id, "user": owner_id, "settings": off})
    publish(world.application, "subprocessors")
    schedule(world)
    run_jobs(world)
    [mail] = [item for item in emails(world) if "sub-processors" in item["payload"]["text"]]
    body = mail["payload"]["text"]
    assert "30 days" in body and "legal@shadow.example" in body and "/legal/subprocessors" in body
    assert "is published and takes effect on 2026-12-01" in body
    assert len(mine(world, world.owner)) == 1


def test_the_job_is_registered_with_the_worker() -> None:
    from app.jobs import HANDLERS

    assert ANNOUNCE_JOB in HANDLERS


def test_the_email_text_is_in_the_recipients_language(monkeypatch) -> None:
    from app.notification_email import render

    monkeypatch.setenv("LEGAL_CONTACT_EMAIL", "legal@shadow.example")
    params = {"document_key": "dpa", "version": 2, "effective_from": "2027-01-15", "acceptance": "required"}
    subject, body = render("legal_document_published", params, locale="fi", organization_name="Northwind", inbox_url="https://x/i", settings_url="https://x/s")
    assert "tietojenkäsittelysopimuksesta" in subject and "2027-01-15" in subject
    assert "30 päivää" in body and "legal@shadow.example" in body and "/legal/dpa" in body
    _, english = render("legal_document_published", params, locale="en", organization_name="Northwind", inbox_url="https://x/i", settings_url="https://x/s")
    assert "data processing agreement" in english and "needs to accept it" in english
