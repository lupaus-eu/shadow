"""Rules for the content fields of Events and Series (Yearclock V2 P11, ADR-0033).

One place checks location and links, so every write path (the event, series,
and occurrence routes, import, Plan Again, Support Access) applies the same
limits.
"""
import re
from datetime import date, time
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

DescriptionFormat = Literal["plain", "markdown"]
LOCATION_MAX = 200
LINKS_MAX = 10
LINK_TITLE_MAX = 100
LINK_URL_MAX = 2048


class LinkItem(BaseModel):
    """One titled ``http(s)`` address."""

    title: str = Field(min_length=1, max_length=LINK_TITLE_MAX)
    url: str = Field(min_length=1, max_length=LINK_URL_MAX)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("must not be blank")
        return value

    @field_validator("url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an http or https address")
        return value


def clean_location(value: str | None) -> str | None:
    """Trim; an empty location is no location."""
    return (value.strip() or None) if value is not None else None


def check_links(items: list[LinkItem] | None) -> list[LinkItem] | None:
    if items is None:
        return None
    if len(items) > LINKS_MAX:
        raise ValueError(f"at most {LINKS_MAX} links")
    seen = set()
    for item in items:
        if item.url in seen:
            raise ValueError("the same address is listed twice")
        seen.add(item.url)
    return items


def links_json(items: list[LinkItem] | list[dict] | None) -> list[dict[str, str]]:
    """The stored form of a link list."""
    return [{"title": item.title, "url": item.url} if isinstance(item, LinkItem) else {"title": item["title"], "url": item["url"]} for item in (items or [])]


_HOST = re.compile(r"^https?://([^/:?#]+)")


def host_title(url: str) -> str:
    """A title for a link that has none: its host name, as the migration gives to old single links (same pattern as its SQL)."""
    match = _HOST.match(url)
    return (match.group(1) if match else url)[:LINK_TITLE_MAX]


def parse_stored_links(value: Any) -> list[dict[str, str]]:
    """Links from a stored value, tolerating the pre-P11 ``external_url`` string that old History entries hold."""
    if isinstance(value, str):
        return [{"title": host_title(value), "url": value}] if value else []
    return links_json(value) if value else []


def clean_time(value: time | None) -> time | None:
    """Times are kept to the minute and carry no time zone: they are read in the Organization's."""
    return value.replace(second=0, microsecond=0, tzinfo=None) if value is not None else None


def check_times(starts_on: date, ends_on: date | None, starts_at: time | None, ends_at: time | None) -> None:
    """An end time needs a start time, and on a single-day Event it is after the start time."""
    if ends_at is not None and starts_at is None:
        raise ValueError("an end time needs a start time")
    if starts_at is not None and ends_at is not None and (ends_on is None or ends_on == starts_on) and ends_at <= starts_at:
        raise ValueError("the end time must be after the start time")


def time_text(value: time | None) -> str | None:
    """``HH:MM`` as the API and the files write it."""
    return value.strftime("%H:%M") if value is not None else None


def parse_time_text(value: str | None) -> time | None:
    """The stored ``HH:MM`` form back to a time."""
    return time.fromisoformat(value) if value else None
