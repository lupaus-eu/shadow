"""The Summary of upcoming Events (Yearclock V2 P8, ADR-0031).

An opt-in email per person and Organization, weekly (Mondays, the next 14 days)
or daily (the next 7 days), written at the first worker pass after 08:00 in the
Organization's time zone. It lists only Events the person may read in the
Yearclocks they chose, and nothing is sent when there is nothing to list. It is
the only message that carries Event content, which is why it is opt-in.
"""
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.access import accessible_yearclock_ids, membership_of
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import BackgroundJob, Event, Lane, NotificationPreference, Organization, OrganizationStatus, SeriesOccurrence, UserAccount, Yearclock
from app.subscription_access import READ_ONLY, effective_state
from app.work_queue import BackgroundJobDraft, OutboxMessageDraft, enqueue_background_job, enqueue_outbox_message
from app.yearclock_reading import readable_links

SUMMARY_JOB = "notifications.summary"
SUMMARY_TOPIC = "summary"
SEND_HOUR = 8
DAYS = {"daily": 7, "weekly": 14}
MAX_LINES = 50
MONDAY = 0

WEEKDAYS = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "fi": ["ma", "ti", "ke", "to", "pe", "la", "su"]}
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TEXT = {
    "en": {"subject": "{organization}: upcoming Events, next {days} days", "intro": "Events starting in the next {days} days in {organization}:", "more": "…and {count} more.", "open": "Open the Yearclock:", "settings": "You get this summary because you chose it. Change or stop it in Notification settings:"},
    "fi": {"subject": "{organization}: tulevat tapahtumat, seuraavat {days} päivää", "intro": "Seuraavien {days} päivän tapahtumat organisaatiossa {organization}:", "more": "…ja {count} muuta.", "open": "Avaa vuosikello:", "settings": "Saat tämän yhteenvedon, koska valitsit sen. Muuta tai lopeta se ilmoitusasetuksissa:"},
}


@dataclass(frozen=True)
class Upcoming:
    starts_on: date
    ends_on: date | None
    title: str
    yearclock_id: UUID
    yearclock: str
    lane: str
    location: str = ""
    starts_at: time | None = None
    ends_at: time | None = None


def _day(value: date, locale: str) -> str:
    weekday = WEEKDAYS[locale][value.weekday()]
    return f"{weekday} {value.day}.{value.month}." if locale == "fi" else f"{weekday} {value.day} {MONTHS_EN[value.month - 1]}"


def _clock(value: time | None) -> str:
    return value.strftime("%H:%M") if value else ""


def _when(item: Upcoming, locale: str) -> str:
    single = not item.ends_on or item.ends_on == item.starts_on
    start, end = _clock(item.starts_at), _clock(item.ends_at)
    if single:
        return f"{_day(item.starts_on, locale)} {start}{'–' + end if end else ''}".strip()
    return f"{_day(item.starts_on, locale)}{' ' + start if start else ''} – {_day(item.ends_on, locale)}{' ' + end if end else ''}"


def upcoming_events(session: Session, organization: Organization, user_account_id: UUID, chosen: list[UUID] | None, start: date, days: int) -> list[Upcoming]:
    """Events the person may read in the chosen (default: every readable, non-archived) Yearclocks that overlap the window."""
    membership = membership_of(session, organization.id, user_account_id)
    if membership is None:
        return []
    readable = accessible_yearclock_ids(session, membership)
    clocks = session.execute(select(Yearclock.id, Yearclock.name).where(Yearclock.id.in_(readable), Yearclock.archived_at.is_(None), Yearclock.deleted_at.is_(None)).order_by(Yearclock.display_order, Yearclock.id)).all()
    end = start + timedelta(days=days - 1)
    skipped = select(SeriesOccurrence.event_id).where(SeriesOccurrence.skipped.is_(True))
    overlap = (Event.deleted_at.is_(None), Event.starts_on <= end, func.coalesce(Event.ends_on, Event.starts_on) >= start, Event.id.not_in(skipped))
    lanes = {lane.id: lane.name for lane in session.scalars(select(Lane).where(Lane.organization_id == organization.id)).all()}
    found: list[Upcoming] = []
    for clock_id, clock_name in clocks:
        if chosen is not None and clock_id not in chosen:
            continue
        for event in session.scalars(select(Event).where(Event.yearclock_id == clock_id, *overlap)).all():
            found.append(Upcoming(event.starts_on, event.ends_on, event.title, clock_id, clock_name, lanes.get(event.lane_id, ""), event.location or "", event.starts_at, event.ends_at))
        links = readable_links(session, organization.id, clock_id, user_account_id)
        if links:
            for event in session.scalars(select(Event).where(Event.lane_id.in_(links.keys()), *overlap)).all():
                found.append(Upcoming(event.starts_on, event.ends_on, event.title, clock_id, clock_name, lanes.get(links[event.lane_id][0], ""), event.location or "", event.starts_at, event.ends_at))
    return sorted(found, key=lambda item: (item.starts_on, item.starts_at is not None, item.starts_at or time.min, item.title, item.yearclock))


def render_summary(items: list[Upcoming], *, locale: str, organization: Organization, days: int, base_url: str) -> tuple[str, str]:
    text = TEXT[locale]
    lines = [text["intro"].format(days=days, organization=organization.name), ""]
    lines += [f"• {_when(item, locale)}: {item.title} ({item.yearclock} · {item.lane})" + (f" — {item.location}" if item.location else "") for item in items[:MAX_LINES]]
    if len(items) > MAX_LINES:
        lines.append(text["more"].format(count=len(items) - MAX_LINES))
    first = items[0]
    lines += ["", f"{text['open']} {base_url}/yearclocks/{first.yearclock_id}", f"{text['settings']} {base_url}/notification-settings"]
    return text["subject"].format(organization=organization.name, days=days), "\n".join(lines)


def send_summaries(session: Session, job: BackgroundJob, now: datetime) -> int:
    """Queue the due Summaries of one Organization; returns how many emails were queued."""
    apply_request_context(session, RequestContext(organization_id=job.organization_id, worker_scope="notifications"))
    organization = session.get(Organization, job.organization_id)
    if organization is None or organization.status != OrganizationStatus.ACTIVE.value or effective_state(organization, now=now) == READ_ONLY:
        return 0
    local = now.astimezone(ZoneInfo(organization.time_zone))
    if local.hour < SEND_HOUR:
        return 0
    today = local.date()
    base = f"{os.getenv('FRONTEND_URL', 'http://localhost:8173').rstrip('/')}/organizations/{organization.id}"
    queued = 0
    for preference in session.scalars(select(NotificationPreference).where(NotificationPreference.organization_id == organization.id, NotificationPreference.summary_frequency != "off")).all():
        if preference.summary_sent_on == today or (preference.summary_frequency == "weekly" and today.weekday() != MONDAY):
            continue
        preference.summary_sent_on = today
        person = session.get(UserAccount, preference.user_id)
        days = DAYS[preference.summary_frequency]
        items = upcoming_events(session, organization, preference.user_id, preference.summary_yearclock_ids, today, days) if person else []
        if not items:
            continue
        locale = person.locale if person.locale in TEXT else organization.default_locale if organization.default_locale in TEXT else "en"
        subject, body = render_summary(items, locale=locale, organization=organization, days=days, base_url=base)
        enqueue_outbox_message(session, OutboxMessageDraft(topic=SUMMARY_TOPIC, payload={"to": person.email, "subject": subject, "text": body, "recipient_id": str(person.id)}, idempotency_key=f"summary:{organization.id}:{person.id}:{today.isoformat()}"))
        queued += 1
    return queued


def schedule_summary_jobs(session_factory: sessionmaker[Session], *, now: datetime) -> int:
    """Enqueue one Summary job per active Organization once its local time has reached the send hour, once per local day."""
    with transaction_session(session_factory, RequestContext(worker_scope="enumerate")) as session:
        organizations = session.execute(select(Organization.id, Organization.time_zone).where(Organization.status == OrganizationStatus.ACTIVE.value)).all()
    due = [(organization_id, now.astimezone(ZoneInfo(zone)).date()) for organization_id, zone in organizations if now.astimezone(ZoneInfo(zone)).hour >= SEND_HOUR]
    for organization_id, day in due:
        with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
            enqueue_background_job(session, BackgroundJobDraft(job_type=SUMMARY_JOB, payload={}, idempotency_key=f"{SUMMARY_JOB}:{organization_id}:{day.isoformat()}"))
    return len(due)
