import pytest
from datetime import date

from app.planning_window import months_between, planning_window


def test_default_window_is_current_calendar_year() -> None:
    assert planning_window(None, today=date(2026, 7, 30)) == (date(2026, 1, 1), date(2026, 12, 31))


def test_window_has_twelve_consecutive_months_across_year_boundary() -> None:
    start, end = planning_window(date(2024, 3, 19), today=date(2026, 1, 1))
    assert (start, end) == (date(2024, 3, 1), date(2025, 2, 28))
    assert months_between(start)[-1] == date(2025, 2, 1)


def test_windows_of_every_length_cover_whole_months() -> None:
    start = date(2026, 11, 20)
    expected = {1: date(2026, 11, 30), 3: date(2027, 1, 31), 6: date(2027, 4, 30), 12: date(2027, 10, 31), 18: date(2028, 4, 30), 24: date(2028, 10, 31)}
    for months, end in expected.items():
        assert planning_window(start, today=date(2026, 9, 25), months=months) == (date(2026, 11, 1), end)
    with pytest.raises(ValueError):
        planning_window(start, today=date(2026, 9, 25), months=5)
