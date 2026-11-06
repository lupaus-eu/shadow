"""iCalendar (.ics) text for exported Events (Yearclock V2 P8, ADR-0031).

Every Event and Occurrence is its own all-day event with a stable UID, so
opening the file again updates the earlier entries in most calendars. There is
no recurrence rule, alarm, or attendee.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

PRODID = "-//Yearclock//Export//EN"
FOLD_OCTETS = 75


def escape_text(value: str) -> str:
    """TEXT escaping of RFC 5545: backslash, semicolon, comma, and line breaks."""
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def fold(line: str) -> str:
    """Split a content line into lines of at most 75 octets, never inside a UTF-8 character."""
    encoded = line.encode("utf-8")
    if len(encoded) <= FOLD_OCTETS:
        return line
    parts: list[str] = []
    current = b""
    limit = FOLD_OCTETS
    for char in line:
        piece = char.encode("utf-8")
        if len(current) + len(piece) > limit:
            parts.append(current.decode("utf-8"))
            current, limit = b"", FOLD_OCTETS - 1
        current += piece
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _day(value: date) -> str:
    return value.strftime("%Y%m%d")


def _instant(day: date, at: time, zone: str) -> str:
    """A wall-clock time in the Organization's zone as a UTC instant, which every calendar reads without a zone definition."""
    return datetime.combine(day, at, tzinfo=ZoneInfo(zone)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def calendar_text(name: str, events: list[dict], *, stamp: datetime, time_zone: str = "UTC") -> str:
    """``events`` hold uid, title, starts_on, ends_on, description, location, links (title and address pairs), categories, and sequence."""
    stamped = stamp.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{escape_text(name)}"]
    for event in events:
        last = event["ends_on"] or event["starts_on"]
        lines += ["BEGIN:VEVENT", f"UID:{event['uid']}", f"DTSTAMP:{stamped}", f"SEQUENCE:{event['sequence']}"]
        if event.get("starts_at") is not None:
            start = _instant(event["starts_on"], event["starts_at"], time_zone)
            # A start time alone is a point in time on a single day and runs through the last day on a longer Event; no duration is invented.
            if event.get("ends_at") is not None:
                end = _instant(last, event["ends_at"], time_zone)
            elif last > event["starts_on"]:
                end = _instant(last + timedelta(days=1), time(0, 0), time_zone)
            else:
                end = start
            lines += [f"DTSTART:{start}", f"DTEND:{end}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{_day(event['starts_on'])}", f"DTEND;VALUE=DATE:{_day(last + timedelta(days=1))}"]
        lines.append(f"SUMMARY:{escape_text(event['title'])}")
        links = event.get("links") or []
        description = "\n\n".join(part for part in (event["description"], "\n".join(f"{title}: {url}" for title, url in links[1:])) if part)
        if description:
            lines.append(f"DESCRIPTION:{escape_text(description)}")
        if event.get("location"):
            lines.append(f"LOCATION:{escape_text(event['location'])}")
        if links:
            lines.append(f"URL:{links[0][1]}")
        if event["categories"]:
            lines.append("CATEGORIES:" + ",".join(escape_text(item) for item in event["categories"]))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(fold(line) + "\r\n" for line in lines)
