from datetime import date


WINDOW_LENGTHS = (1, 3, 6, 12, 18, 24)


def planning_window(start: date | None, *, today: date, months: int = 12) -> tuple[date, date]:
    """Return an inclusive window of whole months beginning on a month boundary (Yearclock V2: 1–24 months)."""
    if months not in WINDOW_LENGTHS:
        raise ValueError(f"window length must be one of {WINDOW_LENGTHS}")
    first = start or date(today.year, 1, 1)
    first = date(first.year, first.month, 1)
    year = first.year + (first.month - 1 + months) // 12
    month = (first.month - 1 + months) % 12 + 1
    return first, date.fromordinal(date(year, month, 1).toordinal() - 1)


def months_between(start: date) -> list[date]:
    return [date(start.year + (start.month - 1 + offset) // 12, (start.month - 1 + offset) % 12 + 1, 1) for offset in range(12)]
