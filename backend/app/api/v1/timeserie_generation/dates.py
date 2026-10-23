from datetime import date as dt_date
from datetime import timedelta

from app.api.v1.org_states.schemas import TimeserieTimeUnit


def is_period_start(time_unit: TimeserieTimeUnit, value_date: dt_date) -> bool:
    """Match the timeserie value date rules of the Organisation States domain."""
    if time_unit == "day":
        return True
    if time_unit == "week":
        return value_date.weekday() == 0
    if time_unit == "month":
        return value_date.day == 1
    return value_date.month == 1 and value_date.day == 1


def period_start(
    start_date: dt_date, time_unit: TimeserieTimeUnit, index: int
) -> dt_date:
    """Return the start date of period `index`, counted from an aligned start.

    Raises `OverflowError` or `ValueError` past the largest representable date.
    """
    if time_unit == "day":
        return start_date + timedelta(days=index)
    if time_unit == "week":
        return start_date + timedelta(weeks=index)
    if time_unit == "month":
        months = start_date.month - 1 + index
        return dt_date(start_date.year + months // 12, months % 12 + 1, 1)
    return dt_date(start_date.year + index, 1, 1)


def period_count(
    start_date: dt_date,
    time_unit: TimeserieTimeUnit,
    end_date: dt_date,
) -> int:
    """Count aligned periods that start on or after an aligned start and on or
    before `end_date` (inclusive)."""
    if time_unit == "day":
        return (end_date - start_date).days + 1
    if time_unit == "week":
        return (end_date - start_date).days // 7 + 1
    if time_unit == "month":
        return (
            (end_date.year - start_date.year) * 12
            + end_date.month
            - start_date.month
            + 1
        )
    return end_date.year - start_date.year + 1


def period_dates(
    start_date: dt_date,
    time_unit: TimeserieTimeUnit,
    count: int,
) -> list[dt_date]:
    return [period_start(start_date, time_unit, index) for index in range(count)]
