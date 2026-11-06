"""Spreadsheet exchange of Events (Yearclock V2 P7, ADR-0030): columns, files, and the hourly limit.

Export and import share one column model, so a file exported from a Yearclock
is a valid template for importing into one.
"""
import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.event_content import time_text
from app.limits import Ceiling
from app.models import AuditEvent

Locale = Literal["en", "fi"]

COLUMNS = ("title", "starts", "ends", "start_time", "end_time", "lane", "category", "labels", "location", "description", "links", "series", "source")
HEADERS: dict[str, dict[str, str]] = {
    "en": {"title": "Title", "starts": "Starts", "ends": "Ends", "start_time": "Start time", "end_time": "End time", "lane": "Lane", "category": "Category", "labels": "Labels", "location": "Location", "description": "Description", "links": "Links", "series": "Series", "source": "Source"},
    "fi": {"title": "Otsikko", "starts": "Alkaa", "ends": "Päättyy", "start_time": "Alkamisaika", "end_time": "Päättymisaika", "lane": "Kehä", "category": "Kategoria", "labels": "Tunnisteet", "location": "Sijainti", "description": "Kuvaus", "links": "Linkit", "series": "Sarja", "source": "Lähde"},
}
FREQUENCY_TEXT = {
    "en": {"WEEKLY": ("Weekly", "Every {n} weeks"), "MONTHLY": ("Monthly", "Every {n} months"), "YEARLY": ("Yearly", "Every {n} years")},
    "fi": {"WEEKLY": ("Viikoittain", "Joka {n}. viikko"), "MONTHLY": ("Kuukausittain", "Joka {n}. kuukausi"), "YEARLY": ("Vuosittain", "Joka {n}. vuosi")},
}
LAST_DAY_TEXT = {"en": "last day of the month", "fi": "kuun viimeinen päivä"}
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
# Audit actions that count toward the hourly limit of exports and imports (previews included).
EXPORT_ACTIONS = ("yearclock.export", "yearclock.import", "yearclock.import_preview")


@dataclass(frozen=True)
class ExportRow:
    title: str
    starts_on: date
    ends_on: date | None
    lane: str
    starts_at: time | None = None
    ends_at: time | None = None
    category: str = ""
    labels: tuple[str, ...] = ()
    description: str = ""
    location: str = ""
    links: tuple[tuple[str, str], ...] = ()
    series: str = ""
    source: str = ""
    uid: str = ""
    version: int = 1


@dataclass
class ExportFile:
    content: bytes
    media_type: str
    extension: str
    rows: int = 0
    notes: list[str] = field(default_factory=list)


def neutralize(value: str) -> str:
    """Stop a spreadsheet from running text as a formula: a leading apostrophe makes it literal text."""
    return f"'{value}" if value and (value.startswith(FORMULA_STARTS) or value.lstrip(" ").startswith(FORMULA_STARTS)) else value


def series_text(locale: Locale, frequency: str, interval: int, last_day: bool) -> str:
    single, several = FREQUENCY_TEXT[locale].get(frequency, (frequency.title(), frequency.title()))
    text = single if interval == 1 else several.format(n=interval)
    return f"{text}, {LAST_DAY_TEXT[locale]}" if last_day and frequency == "MONTHLY" else text


def links_cell(links: tuple[tuple[str, str], ...]) -> str:
    """One ``Title | address`` per line."""
    return "\n".join(f"{title} | {url}" for title, url in links)


def _cells(row: ExportRow) -> list[object]:
    return [
        neutralize(row.title), row.starts_on, row.ends_on, time_text(row.starts_at) or "", time_text(row.ends_at) or "", neutralize(row.lane), neutralize(row.category), neutralize(", ".join(row.labels)),
        neutralize(row.location), neutralize(row.description), neutralize(links_cell(row.links)), neutralize(row.series), neutralize(row.source),
    ]


def build_xlsx(rows: list[ExportRow], locale: Locale) -> ExportFile:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(title="Events" if locale == "en" else "Tapahtumat")
    for column, width in zip("ABCDEFGHIJKLM", (36, 12, 12, 12, 12, 18, 18, 24, 28, 48, 44, 22, 22)):
        sheet.column_dimensions[column].width = width
    header = []
    for name in COLUMNS:
        cell = WriteOnlyCell(sheet, value=HEADERS[locale][name])
        cell.font = Font(bold=True)
        header.append(cell)
    sheet.append(header)
    for row in rows:
        values = []
        for value in _cells(row):
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, date):
                cell.number_format = "yyyy-mm-dd"
            values.append(cell)
        sheet.append(values)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return ExportFile(buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx", len(rows))


def build_ics(rows: list[ExportRow], name: str, stamp: datetime, time_zone: str = "UTC") -> ExportFile:
    """The rows as an iCalendar file; a row without a UID of its own cannot be exported."""
    from app.ical import calendar_text

    events = [{"uid": row.uid, "title": row.title, "starts_on": row.starts_on, "ends_on": row.ends_on, "description": row.description, "location": row.location, "links": row.links, "starts_at": row.starts_at, "ends_at": row.ends_at,
               "categories": [item for item in (row.category, *row.labels) if item], "sequence": row.version - 1} for row in rows]
    return ExportFile(calendar_text(name, events, stamp=stamp, time_zone=time_zone).encode("utf-8"), "text/calendar; charset=utf-8", "ics", len(rows))


def build_csv(rows: list[ExportRow], locale: Locale) -> ExportFile:
    """UTF-8 with a byte order mark; Finnish spreadsheets expect a semicolon, others a comma."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";" if locale == "fi" else ",", lineterminator="\r\n")
    writer.writerow([HEADERS[locale][name] for name in COLUMNS])
    for row in rows:
        writer.writerow([value.isoformat() if isinstance(value, date) else ("" if value is None else value) for value in _cells(row)])
    return ExportFile(("﻿" + buffer.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", "csv", len(rows))


def require_exchange_quota(session: Session, user_account_id: UUID, organization_id: UUID, actions: tuple[str, ...], ceiling: Ceiling) -> None:
    """Refuse with 429 when the user already used the hourly allowance; the Audit Log is the counter."""
    now = session.scalar(select(func.now()))
    since = now - timedelta(hours=1)
    recent = session.scalars(select(AuditEvent.occurred_at).where(AuditEvent.actor_user_account_id == user_account_id, AuditEvent.organization_id == organization_id, AuditEvent.action.in_(actions), AuditEvent.occurred_at > since).order_by(AuditEvent.occurred_at)).all()
    if len(recent) >= ceiling.maximum:
        retry_after = max(1, int((recent[len(recent) - ceiling.maximum] + timedelta(hours=1) - now).total_seconds()) + 1)
        raise HTTPException(status_code=429, detail={"reason": "rate_limited", "limit": ceiling.name, "maximum": ceiling.maximum, "retry_after_seconds": retry_after}, headers={"Retry-After": str(retry_after)})


def file_name(yearclock_name: str, suffix: str, extension: str) -> str:
    """An ASCII file name: accents removed, anything else a hyphen."""
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", yearclock_name).encode("ascii", "ignore").decode().lower()).strip("-") or "yearclock"
    return f"{slug}-{suffix}.{extension}"


# ── Import (Yearclock V2 P7 ticket 03) ─────────────────────────────────────────

IMPORT_ROWS = Ceiling("import_rows", "LIMIT_IMPORT_ROWS", 1000)
IMPORT_MAX_BYTES = Ceiling("import_max_bytes", "IMPORT_MAX_BYTES", 2 * 1024 * 1024)
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_RAW_ROWS = 20_000
REQUIRED_COLUMNS = ("title", "starts", "lane")
IMPORT_COLUMNS = ("title", "starts", "ends", "start_time", "end_time", "lane", "category", "labels", "location", "description", "links")


class ImportFileError(Exception):
    """The file cannot be read as a spreadsheet of Events; ``reason`` is machine readable."""

    def __init__(self, reason: str, **detail: object) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def normalize(text: str) -> str:
    """The comparison form of a name: accents removed, lower case, single spaces."""
    stripped = "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", stripped).strip().casefold()


HEADER_KEYS = {normalize(title): key for titles in HEADERS.values() for key, title in titles.items()}
# Files made before Yearclock V2 P11 have one address in a column called Link.
HEADER_KEYS.update({"link": "links", "linkki": "links"})


def unneutralize(value: str) -> str:
    """Undo the guard that an export puts before text that looks like a formula."""
    return value[1:] if value.startswith("'") and value[1:].lstrip(" ").startswith(FORMULA_STARTS) else value


_TIME_TEXT = re.compile(r"^(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?$")


def read_time(value: object) -> tuple[time | None, bool]:
    """A start or end time from a spreadsheet cell: ``14:00``, ``9.30``, a time cell, or a day fraction. Returns (time, invalid)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, False
    if isinstance(value, datetime):
        value = value.time()
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0, tzinfo=None), False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 0 <= value < 1:
            minutes = round(value * 24 * 60)
            return (time(minutes // 60 % 24, minutes % 60) if minutes < 24 * 60 else None), minutes >= 24 * 60
        return None, True
    match = _TIME_TEXT.match(str(value).strip())
    if match and int(match.group(1)) < 24 and int(match.group(2)) < 60 and int(match.group(3) or 0) < 60:
        return time(int(match.group(1)), int(match.group(2))), False
    return None, True


def cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date)):
        return (value.date() if isinstance(value, datetime) else value).isoformat()
    return unneutralize(str(value).strip())


@dataclass
class ParsedRow:
    number: int
    cells: dict[str, object]


def _rows_from_cells(raw_rows) -> tuple[list[str | None], list[ParsedRow]]:
    """The header row's column keys (None for columns we do not know) and the non-blank data rows with their sheet row numbers."""
    header: list[str | None] | None = None
    rows: list[ParsedRow] = []
    for number, values in enumerate(raw_rows, start=1):
        if number > MAX_RAW_ROWS:
            raise ImportFileError("too_many_rows", maximum=IMPORT_ROWS.maximum)
        if all(value is None or str(value).strip() == "" for value in values):
            continue
        if header is None:
            header = [HEADER_KEYS.get(normalize(str(value))) if value is not None else None for value in values]
            continue
        rows.append(ParsedRow(number, {key: value for key, value in zip(header, values) if key is not None}))
        if len(rows) > IMPORT_ROWS.maximum:
            raise ImportFileError("too_many_rows", maximum=IMPORT_ROWS.maximum)
    return header or [], rows


def read_xlsx(content: bytes) -> tuple[list[str | None], list[ParsedRow]]:
    import zipfile
    from zipfile import BadZipFile

    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except BadZipFile as error:
        raise ImportFileError("unreadable_file") from error
    names = archive.namelist()
    if any(name.lower().endswith("vbaproject.bin") for name in names):
        raise ImportFileError("macros_not_allowed")
    if "xl/workbook.xml" not in names or sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
        raise ImportFileError("unreadable_file")
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        return _rows_from_cells(sheet.iter_rows(values_only=True))
    except ImportFileError:
        raise
    except (InvalidFileException, KeyError, ValueError, IndexError, OSError) as error:
        raise ImportFileError("unreadable_file") from error


def read_csv(content: bytes) -> tuple[list[str | None], list[ParsedRow]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp1252")
        except UnicodeDecodeError as error:
            raise ImportFileError("unreadable_file") from error
    first = text.split("\n", 1)[0]
    delimiter = max((";", ",", "\t"), key=first.count)
    if first.count(delimiter) == 0:
        raise ImportFileError("unreadable_file")
    return _rows_from_cells(csv.reader(io.StringIO(text), delimiter=delimiter))


def build_template(locale: Locale, lanes: list[str], categories: list[str], labels: list[str]) -> bytes:
    """A workbook with the empty column titles and a second sheet listing the names the import accepts."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Events" if locale == "en" else "Tapahtumat"
    sheet.append([HEADERS[locale][key] for key in IMPORT_COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for column, width in zip("ABCDEFGHIJK", (36, 12, 12, 12, 12, 18, 18, 24, 28, 48, 44)):
        sheet.column_dimensions[column].width = width
    names = workbook.create_sheet(title="Allowed values" if locale == "en" else "Sallitut arvot")
    titles = ("Lanes", "Categories", "Labels") if locale == "en" else ("Kehät", "Kategoriat", "Tunnisteet")
    names.append(list(titles))
    for cell in names[1]:
        cell.font = Font(bold=True)
    for index in range(max(len(lanes), len(categories), len(labels), 0)):
        names.append([neutralize(items[index]) if index < len(items) else None for items in (lanes, categories, labels)])
    for column in "ABC":
        names.column_dimensions[column].width = 28
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
