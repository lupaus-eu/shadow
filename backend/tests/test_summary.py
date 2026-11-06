"""The Summary of upcoming Events (Yearclock V2, P8 ticket 04)."""
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text

from app.database import RequestContext, transaction_session
from app.jobs import run_one_background_job
from app.models import BackgroundJob
from app.summary import SUMMARY_JOB, schedule_summary_jobs, send_summaries
from test_notifications import World, stack  # noqa: F401 - the fixture

# Monday 2026-10-05, 09:30 in Helsinki (UTC+3 in summer time).
MONDAY = datetime(2026, 10, 5, 6, 30, tzinfo=UTC)


def run(world, now=MONDAY):
    with transaction_session(world.application.state.session_factory, RequestContext(organization_id=UUID(world.organization_id))) as session:
        return send_summaries(session, BackgroundJob(id=uuid4(), organization_id=UUID(world.organization_id), job_type=SUMMARY_JOB, payload={}, idempotency_key="x"), now)


def mails(world):
    with world.application.state.database_engine.begin() as connection:
        return [row.payload for row in connection.execute(text("SELECT payload FROM outbox_messages WHERE topic = 'summary' AND organization_id = :org ORDER BY created_at"), {"org": world.organization_id})]


def choose(client, world, frequency, yearclock_ids=None):
    response = client.put(f"{world.org}/notification-settings", json={"summary": {"frequency": frequency, "yearclock_ids": yearclock_ids}})
    assert response.status_code == 200, response.text
    return response.json()


def event(world, title, starts_on, **extra):
    response = world.owner.post(f"{world.base}/events", json={"title": title, "lane_id": world.clock["lanes"][0]["id"], "starts_on": starts_on, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_daily_summary_lists_the_next_seven_days_and_only_once_a_day(database_url, stack) -> None:
    world = World(stack, database_url, "sum-daily")
    event(world, "Today planning", "2026-10-05")
    event(world, "Edge of the week", "2026-10-11")
    event(world, "Next week", "2026-10-12")
    event(world, "Yesterday", "2026-10-04")
    event(world, "Long running", "2026-10-01", ends_on="2026-10-06")
    gone = event(world, "Deleted", "2026-10-06")
    assert world.owner.delete(f"{world.base}/events/{gone['id']}", params={"expected_version": gone["version"]}).status_code in {200, 204}
    assert choose(world.owner, world, "daily")["summary"] == {"frequency": "daily", "yearclock_ids": None}
    assert run(world) == 1
    [mail] = mails(world)
    assert mail["to"] == "sum-daily@example.com" and "next 7 days" in mail["subject"]
    body = mail["text"]
    assert "Today planning" in body and "Edge of the week" in body and "Long running" in body
    assert "Next week" not in body and "Yesterday" not in body and "Deleted" not in body
    assert "Mon 5 Oct: Today planning (Northwind" in body or "Mon 5 Oct: Today planning (" in body
    assert f"/yearclocks/{world.clock['id']}" in body and "/notification-settings" in body
    assert run(world) == 0 and len(mails(world)) == 1  # already sent for this day
    assert run(world, MONDAY + timedelta(days=1)) == 1 and len(mails(world)) == 2


def test_a_weekly_summary_goes_out_on_mondays_for_two_weeks_and_never_empty(database_url, stack) -> None:
    world = World(stack, database_url, "sum-weekly")
    choose(world.owner, world, "weekly")
    assert run(world) == 0 and mails(world) == []  # Monday, but nothing to list
    event(world, "In ten days", "2026-10-15")
    event(world, "In three weeks", "2026-10-27")
    tuesday = MONDAY + timedelta(days=1)
    assert run(world, tuesday) == 0
    # The empty Monday run marked the day; the next Monday sends.
    next_monday = MONDAY + timedelta(days=7)
    assert run(world, next_monday) == 1
    # The window is the 14 days from the next Monday (12-25 October): the event on the 15th is in, the one on the 27th is not.
    assert "In ten days" in mails(world)[0]["text"] and "In three weeks" not in mails(world)[0]["text"] and "next 14 days" in mails(world)[0]["subject"]


def test_nothing_is_sent_before_eight_local_time_and_summer_and_winter_time_are_respected(database_url, stack) -> None:
    world = World(stack, database_url, "sum-hour")
    event(world, "Soon", "2026-10-06")
    choose(world.owner, world, "daily")
    assert run(world, datetime(2026, 10, 5, 4, 30, tzinfo=UTC)) == 0  # 07:30 in Helsinki (UTC+3)
    assert run(world, datetime(2026, 10, 5, 5, 30, tzinfo=UTC)) == 1  # 08:30
    event(world, "Winter", "2026-11-03")
    assert run(world, datetime(2026, 11, 2, 5, 30, tzinfo=UTC)) == 0  # 07:30 in Helsinki (UTC+2 after the change)
    assert run(world, datetime(2026, 11, 2, 6, 30, tzinfo=UTC)) == 1  # 08:30


def test_people_see_only_what_they_may_read_in_the_yearclocks_they_chose(database_url, stack) -> None:
    world = World(stack, database_url, "sum-access")
    event(world, "Open plan", "2026-10-06")
    secret = world.owner.post(f"{world.org}/yearclocks", json={"name": "Board only"}).json()
    lane = world.owner.get(f"{world.org}/yearclocks/{secret['id']}").json()["lanes"][0]["id"] if world.owner.get(f"{world.org}/yearclocks/{secret['id']}").status_code == 200 else secret["lanes"][0]["id"]
    assert world.owner.post(f"{world.org}/yearclocks/{secret['id']}/events", json={"title": "Board secret", "lane_id": lane, "starts_on": "2026-10-06"}).status_code == 201
    viewer, viewer_id, _ = world.person("viewer")
    nobody, _, _ = world.person("nobody")
    assert world.owner.put(f"{world.base}/access", json={"user_account_id": viewer_id, "role": "viewer"}).status_code == 200
    choose(viewer, world, "daily")
    choose(nobody, world, "daily")
    choose(world.owner, world, "daily", [secret["id"]])
    assert run(world) == 2
    by_recipient = {mail["to"]: mail["text"] for mail in mails(world)}
    assert "Open plan" in by_recipient["sum-access-viewer@example.com"] and "Board secret" not in by_recipient["sum-access-viewer@example.com"]
    assert "Board secret" in by_recipient["sum-access@example.com"] and "Open plan" not in by_recipient["sum-access@example.com"]
    assert "sum-access-nobody@example.com" not in by_recipient
    assert viewer.put(f"{world.org}/notification-settings", json={"summary": {"frequency": "daily", "yearclock_ids": [secret["id"]]}}).status_code == 422


def test_archived_yearclocks_are_left_out_and_finnish_readers_get_finnish(database_url, stack) -> None:
    world = World(stack, database_url, "sum-fi")
    event(world, "Palaveri", "2026-10-07")
    with world.application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE user_accounts SET locale = 'fi' WHERE email = 'sum-fi@example.com'"))
    choose(world.owner, world, "daily")
    assert run(world) == 1
    [mail] = mails(world)
    assert "seuraavat 7 päivää" in mail["subject"] and "ke 7.10.: Palaveri" in mail["text"]
    with world.application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE yearclocks SET archived_at = now() WHERE id = :id"), {"id": world.clock["id"]})
        connection.execute(text("UPDATE notification_preferences SET summary_sent_on = NULL"))
    assert run(world, MONDAY + timedelta(days=1)) == 0


def test_summaries_stop_for_removed_people_and_read_only_or_pending_deletion_organizations(database_url, stack) -> None:
    world = World(stack, database_url, "sum-stop")
    member, user_id, membership = world.person("member")
    event(world, "Planning", "2026-10-06")
    assert world.owner.put(f"{world.base}/access", json={"user_account_id": user_id, "role": "viewer"}).status_code == 200
    choose(member, world, "daily")
    assert world.owner.delete(f"{world.org}/memberships/{membership['id']}", params={"expected_version": membership["version"]}).status_code == 204
    assert run(world) == 0
    choose(world.owner, world, "daily")
    with world.application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'grace', grace_expires_at = :past WHERE id = :id"), {"past": MONDAY - timedelta(days=1), "id": world.organization_id})
    assert run(world) == 0
    with world.application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'active', grace_expires_at = NULL, status = 'pending_deletion', deletion_requested_at = now() WHERE id = :id"), {"id": world.organization_id})
    assert run(world) == 0
    assert mails(world) == []


def test_one_job_per_organization_and_local_day_is_scheduled_after_the_send_hour(database_url, stack) -> None:
    world = World(stack, database_url, "sum-schedule")
    factory = world.application.state.session_factory
    before = datetime(2026, 10, 5, 2, 0, tzinfo=UTC)
    assert schedule_summary_jobs(factory, now=before) >= 0
    def jobs():
        with world.application.state.database_engine.begin() as connection:
            return connection.execute(text("SELECT count(*) FROM background_jobs WHERE job_type = :type AND organization_id = :org"), {"type": SUMMARY_JOB, "org": world.organization_id}).scalar()
    assert jobs() == 0
    schedule_summary_jobs(factory, now=MONDAY)
    schedule_summary_jobs(factory, now=MONDAY + timedelta(hours=3))
    assert jobs() == 1
    schedule_summary_jobs(factory, now=MONDAY + timedelta(days=1))
    assert jobs() == 2


def test_the_job_runs_through_the_background_queue(database_url, stack) -> None:
    world = World(stack, database_url, "sum-queue")
    event(world, "Queued", "2026-10-06")
    choose(world.owner, world, "daily")
    factory = world.application.state.session_factory
    schedule_summary_jobs(factory, now=MONDAY)
    ran = 0
    while run_one_background_job(factory, now=lambda: MONDAY, organization_id=UUID(world.organization_id)):
        ran += 1
        assert ran < 20
    assert len(mails(world)) == 1 and "Queued" in mails(world)[0]["text"]


def test_the_summary_choice_is_kept_per_person(database_url, stack) -> None:
    world = World(stack, database_url, "sum-choice")
    member, _, _ = world.person("member")
    assert member.get(f"{world.org}/notification-settings").json()["summary"] == {"frequency": "off", "yearclock_ids": None}
    choose(world.owner, world, "weekly", [world.clock["id"]])
    assert member.get(f"{world.org}/notification-settings").json()["summary"]["frequency"] == "off"
    assert world.owner.get(f"{world.org}/notification-settings").json()["summary"] == {"frequency": "weekly", "yearclock_ids": [world.clock["id"]]}
    assert world.owner.put(f"{world.org}/notification-settings", json={"summary": {"frequency": "monthly"}}).status_code == 422
