from datetime import date
from itertools import islice
import pytest

from app.recurrence import occurrences, to_rrule

def test_monthly_anchor_falls_back_then_returns_to_anchor() -> None:
    result = list(islice(occurrences(starts_on=date(2024, 1, 31), frequency="MONTHLY"), 4))
    assert result == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30)]
def test_last_day_rule_and_february_twenty_ninth_yearly_skip() -> None:
    monthly = list(islice(occurrences(starts_on=date(2024, 1, 12), frequency="MONTHLY", last_day=True), 3))
    yearly = list(islice(occurrences(starts_on=date(2024, 2, 29), frequency="YEARLY"), 2))
    assert monthly == [date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)]
    assert yearly == [date(2024, 2, 29), date(2028, 2, 29)]


def test_yearly_occurrence_count_counts_generated_dates_not_skipped_years() -> None:
    result = list(
        occurrences(
            starts_on=date(2024, 2, 29),
            frequency="YEARLY",
            count=3,
        )
    )

    assert result == [date(2024, 2, 29), date(2028, 2, 29), date(2032, 2, 29)]


def test_weekly_interval_keeps_one_weekday_and_stops_at_until() -> None:
    result = list(occurrences(starts_on=date(2026, 1, 6), frequency="WEEKLY", interval=2, until=date(2026, 2, 17)))
    assert result == [date(2026, 1, 6), date(2026, 1, 20), date(2026, 2, 3), date(2026, 2, 17)]
    assert {item.weekday() for item in result} == {1}


def test_monthly_interval_and_count() -> None:
    result = list(occurrences(starts_on=date(2026, 1, 30), frequency="MONTHLY", interval=3, count=4))
    assert result == [date(2026, 1, 30), date(2026, 4, 30), date(2026, 7, 30), date(2026, 10, 30)]


def test_supported_rules_have_an_rrule_and_unsupported_ones_are_rejected() -> None:
    assert to_rrule(starts_on=date(2026, 1, 6), frequency="WEEKLY", interval=2) == "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU"
    assert to_rrule(starts_on=date(2026, 1, 31), frequency="MONTHLY", count=12) == "FREQ=MONTHLY;INTERVAL=1;BYMONTHDAY=31;COUNT=12"
    assert to_rrule(starts_on=date(2026, 1, 12), frequency="MONTHLY", last_day=True) == "FREQ=MONTHLY;INTERVAL=1;BYMONTHDAY=-1"
    assert to_rrule(starts_on=date(2024, 2, 29), frequency="YEARLY", until=date(2032, 3, 1)) == "FREQ=YEARLY;INTERVAL=1;BYMONTH=2;BYMONTHDAY=29;UNTIL=20320301"
    for invalid in ({"frequency": "DAILY"}, {"frequency": "WEEKLY", "interval": 0}, {"frequency": "YEARLY", "last_day": True}, {"frequency": "MONTHLY", "until": date(2027, 1, 1), "count": 3}):
        with pytest.raises(ValueError):
            to_rrule(starts_on=date(2026, 1, 1), **invalid)
    for frequency, interval in (("DAILY", 1), ("WEEKLY", 0)):
        with pytest.raises(ValueError):
            next(occurrences(starts_on=date(2026, 1, 1), frequency=frequency, interval=interval))

