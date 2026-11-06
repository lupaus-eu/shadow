"""Property-based recurrence tests (PRD testing decision T3, ADR-0026)."""
import calendar
from datetime import date, timedelta
from itertools import islice

from hypothesis import given, settings
from hypothesis import strategies as st

from app.recurrence import occurrences, to_rrule

starts = st.dates(min_value=date(2000, 1, 1), max_value=date(2090, 12, 31))
intervals = st.integers(min_value=1, max_value=12)


def _month_index(value: date) -> int:
    return value.year * 12 + value.month - 1


@settings(max_examples=300)
@given(starts, intervals, st.booleans())
def test_monthly_dates_keep_the_anchor_day_or_fall_back_to_month_end(start: date, interval: int, last_day: bool) -> None:
    dates = list(islice(occurrences(starts_on=start, frequency="MONTHLY", interval=interval, last_day=last_day), 30))
    for index, value in enumerate(dates):
        month_end = calendar.monthrange(value.year, value.month)[1]
        assert _month_index(value) == _month_index(start) + index * interval
        assert value.day == (month_end if last_day else min(start.day, month_end))


@settings(max_examples=300)
@given(starts, intervals)
def test_weekly_dates_keep_the_weekday_and_the_spacing(start: date, interval: int) -> None:
    dates = list(islice(occurrences(starts_on=start, frequency="WEEKLY", interval=interval), 30))
    assert all(value.weekday() == start.weekday() for value in dates)
    assert all(later - earlier == timedelta(weeks=interval) for earlier, later in zip(dates, dates[1:]))


@settings(max_examples=300)
@given(starts, st.integers(min_value=1, max_value=4))
def test_yearly_dates_keep_month_and_day_and_skip_missing_leap_days(start: date, interval: int) -> None:
    dates = list(islice(occurrences(starts_on=start, frequency="YEARLY", interval=interval), 12))
    assert all((value.month, value.day) == (start.month, start.day) for value in dates)
    assert all((value.year - start.year) % interval == 0 for value in dates)
    if (start.month, start.day) == (2, 29):
        assert all(calendar.isleap(value.year) for value in dates)
    else:
        assert [value.year for value in dates] == [start.year + index * interval for index in range(12)]


@settings(max_examples=300)
@given(starts, st.sampled_from(["WEEKLY", "MONTHLY", "YEARLY"]), intervals, st.integers(min_value=1, max_value=40))
def test_count_limits_the_number_of_generated_dates(start: date, frequency: str, interval: int, count: int) -> None:
    dates = list(occurrences(starts_on=start, frequency=frequency, interval=min(interval, 4) if frequency == "YEARLY" else interval, count=count))
    assert len(dates) == count
    assert dates == sorted(set(dates))


@settings(max_examples=300)
@given(starts, st.sampled_from(["WEEKLY", "MONTHLY", "YEARLY"]), intervals, st.integers(min_value=0, max_value=3000))
def test_until_is_inclusive_and_never_exceeded(start: date, frequency: str, interval: int, days: int) -> None:
    until = start + timedelta(days=days)
    bounded = list(occurrences(starts_on=start, frequency=frequency, interval=interval, until=until))
    unbounded = list(islice(occurrences(starts_on=start, frequency=frequency, interval=interval), len(bounded) + 1))
    assert all(value <= until for value in bounded)
    assert bounded == unbounded[: len(bounded)]
    assert len(unbounded) == len(bounded) or unbounded[len(bounded)] > until


@settings(max_examples=200)
@given(starts, st.sampled_from(["WEEKLY", "MONTHLY", "YEARLY"]), intervals, st.integers(min_value=1, max_value=30))
def test_generation_is_deterministic_and_restartable(start: date, frequency: str, interval: int, count: int) -> None:
    first = list(occurrences(starts_on=start, frequency=frequency, interval=interval, count=count))
    again = list(occurrences(starts_on=start, frequency=frequency, interval=interval, count=count))
    assert first == again
    assert to_rrule(starts_on=start, frequency=frequency, interval=interval, count=count).startswith(f"FREQ={frequency};INTERVAL={interval}")
