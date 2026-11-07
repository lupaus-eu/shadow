"""Reading and writing metric values as CSV or Excel tables.

Two layouts are read. *Wide*: the first column is the month and every other column is a metric
(by key or name). *Long*: columns ``metric``, ``period`` and ``value``. Months are written as
``2025-03``, ``2025-03-01``, ``3.2025``, ``1.3.2025`` or ``3/2025``, or are Excel dates. Empty
cells are ignored. A semicolon, comma or tab separates CSV columns and a decimal comma is read.
"""

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook, load_workbook

from app.metric_engine import month_start

MAX_BYTES = 5_000_000
MAX_CELLS = 20_000
PERIOD_HEADERS = {"period", "month", "date", "kuukausi", "jakso", "pvm"}
METRIC_HEADERS = {"metric", "key", "mittari"}
VALUE_HEADERS = {"value", "arvo"}


class ImportError_(ValueError):
    """The file cannot be read as a table of metric values."""


@dataclass
class Parsed:
    """Values by metric label (as written in the file) and the cells that could not be read."""

    values: dict[str, dict[date, float]] = field(default_factory=dict)
    invalid_cells: int = 0


def _period(cell: object) -> date | None:
    if isinstance(cell, datetime):
        return month_start(cell.date())
    if isinstance(cell, date):
        return month_start(cell)
    text = str(cell or "").strip()
    for pattern, order in ((r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$", "ym"), (r"^(?:\d{1,2}\.)?(\d{1,2})\.(\d{4})$", "my"), (r"^(\d{1,2})/(\d{4})$", "my")):
        if match := re.match(pattern, text):
            year, month = (int(match.group(1)), int(match.group(2))) if order == "ym" else (int(match.group(2)), int(match.group(1)))
            return date(year, month, 1) if 1 <= month <= 12 and 1 <= year <= 9999 else None
    return None


def _number(cell: object) -> float | None:
    if isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    text = str(cell or "").strip().replace(" ", "").replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        value = float(Decimal(text))
    except InvalidOperation:
        return None
    return value if value == value and abs(value) != float("inf") else None


def _csv_rows(data: bytes) -> list[list[object]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    sample = text[:4096]
    delimiter = max(";,\t", key=sample.count) if any(sample.count(item) for item in ";,\t") else ","
    return [list(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _xlsx_rows(data: bytes) -> Iterator[list[object]]:
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as error:  # openpyxl raises several kinds for a file that is not a workbook
        raise ImportError_("the file is not a readable Excel workbook") from error
    sheet = workbook.worksheets[0] if workbook.worksheets else None
    if sheet is None:
        raise ImportError_("the workbook has no sheet")
    for row in sheet.iter_rows(values_only=True):
        yield list(row)


def parse_table(data: bytes, filename: str) -> Parsed:
    if len(data) > MAX_BYTES:
        raise ImportError_("the file is too large")
    is_xlsx = filename.lower().endswith((".xlsx", ".xlsm")) or data[:2] == b"PK"
    rows = [row for row in (_xlsx_rows(data) if is_xlsx else _csv_rows(data)) if any(str(cell or "").strip() for cell in row)]
    if len(rows) < 2:
        raise ImportError_("the file needs a header row and at least one data row")
    header = [str(cell or "").strip() for cell in rows[0]]
    lowered = [item.lower() for item in header]
    cells = sum(len(row) for row in rows)
    if cells > MAX_CELLS:
        raise ImportError_("the file has too many cells")
    parsed = Parsed()
    long = next((i for i, item in enumerate(lowered) if item in METRIC_HEADERS), None)
    when = next((i for i, item in enumerate(lowered) if item in PERIOD_HEADERS), None)
    amount = next((i for i, item in enumerate(lowered) if item in VALUE_HEADERS), None)
    if long is not None and when is not None and amount is not None:
        for row in rows[1:]:
            row = row + [None] * (len(header) - len(row))
            label, period, cell = str(row[long] or "").strip(), _period(row[when]), row[amount]
            if not label or not str(cell if cell is not None else "").strip():
                continue
            number = _number(cell)
            if period is None or number is None:
                parsed.invalid_cells += 1
                continue
            parsed.values.setdefault(label, {})[period] = number
        return parsed
    if len(header) < 2:
        raise ImportError_("the file needs a month column and at least one metric column")
    for row in rows[1:]:
        row = row + [None] * (len(header) - len(row))
        period = _period(row[0])
        if period is None:
            parsed.invalid_cells += sum(1 for cell in row[1:] if str(cell if cell is not None else "").strip())
            continue
        for label, cell in zip(header[1:], row[1:]):
            if not label or cell is None or not str(cell).strip():
                continue
            number = _number(cell)
            if number is None:
                parsed.invalid_cells += 1
                continue
            parsed.values.setdefault(label, {})[period] = number
    return parsed


def series_table(columns: list[tuple[str, dict[date, float]]]) -> list[list[object]]:
    """The wide layout: a header row, then one row per month from the first to the last value."""
    periods = sorted({period for _, series in columns for period in series})
    if not periods:
        return [["period", *[label for label, _ in columns]]]
    rows: list[list[object]] = [["period", *[label for label, _ in columns]]]
    current = periods[0]
    while current <= periods[-1]:
        rows.append([current.strftime("%Y-%m"), *[series.get(current) for _, series in columns]])
        index = current.year * 12 + current.month
        current = date(index // 12, index % 12 + 1, 1)
    return rows


def csv_bytes(rows: list[list[object]]) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows([["" if cell is None else cell for cell in row] for row in rows])
    return buffer.getvalue().encode("utf-8-sig")


def workbook_bytes(sheets: dict[str, list[list[object]]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title[:31])
        for row in rows:
            sheet.append([_safe(cell) for cell in row])
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(60, max(10, max(len(str(cell.value or "")) for cell in column) + 2))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _safe(cell: object) -> object:
    """A text cell that starts like a formula is stored as text, so a spreadsheet never runs it."""
    if isinstance(cell, str) and cell[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + cell
    return cell
