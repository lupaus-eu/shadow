import math
import warnings
from collections.abc import Iterator
from datetime import date
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.models import TimeserieValue
from app.api.v1.org_states.schemas import (
    ScenarioCreateRequest,
    TimeserieCreateRequest,
    TimeserieTimeUnit,
    TimeserieValuesPatchRequest,
)
from app.api.v1.org_twin_structure.models import Metamodel
from app.api.v1.organisations import service as organisations_service
from app.api.v1.organisations.schemas import OrganisationCreateRequest
from app.api.v1.timeserie_generation.generator import (
    GENERATOR_VERSION,
    TimeserieGenerationError,
    generate,
)
from app.api.v1.timeserie_generation.schemas import (
    MAX_GENERATED_POINTS,
    TimeserieGenerationSpec,
)
from app.api.v1.users.models import User
from app.core.models import Base

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

ACTOR_USER_ID = 7


def _spec(**overrides: Any) -> TimeserieGenerationSpec:
    payload: dict[str, Any] = {
        "startDate": "2026-01-01",
        "periods": 12,
        "timeUnit": "month",
        "baseLevel": 100,
        "decimals": 6,
        "seed": 1,
    }
    payload.update(overrides)
    return TimeserieGenerationSpec.model_validate(payload)


def _values(spec: TimeserieGenerationSpec) -> list[float]:
    return [point.value for point in generate(spec)]


def _dates(spec: TimeserieGenerationSpec) -> list[date]:
    return [point.date for point in generate(spec)]


NOISY = {
    "periods": 200,
    "timeUnit": "day",
    "noise": {"std": 5, "ar1": 0.5},
    "seasonality": [{"period": 7, "amplitude": 0.2, "mode": "multiplicative"}],
}


def test_generator_version_is_recorded() -> None:
    assert GENERATOR_VERSION == 1


def test_same_spec_and_seed_give_identical_output() -> None:
    first = generate(_spec(**NOISY, seed=42))
    second = generate(_spec(**NOISY, seed=42))

    assert first == second


def test_different_seed_gives_different_output() -> None:
    assert _values(_spec(**NOISY, seed=42)) != _values(_spec(**NOISY, seed=43))


def test_spec_round_trips_through_its_json_form() -> None:
    spec = _spec(**NOISY, levelShifts=[{"date": "2026-02-01", "delta": 3}])
    stored = spec.model_dump(mode="json", by_alias=True)

    assert generate(TimeserieGenerationSpec.model_validate(stored)) == generate(spec)


@pytest.mark.parametrize(
    ("time_unit", "start", "expected"),
    [
        ("day", "2026-02-27", [date(2026, 2, 27), date(2026, 2, 28), date(2026, 3, 1)]),
        (
            "week",
            "2026-12-28",
            [date(2026, 12, 28), date(2027, 1, 4), date(2027, 1, 11)],
        ),
        (
            "month",
            "2026-11-01",
            [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)],
        ),
        ("year", "2027-01-01", [date(2027, 1, 1), date(2028, 1, 1), date(2029, 1, 1)]),
    ],
)
def test_dates_follow_time_unit_alignment(
    time_unit: TimeserieTimeUnit,
    start: str,
    expected: list[date],
) -> None:
    assert _dates(_spec(startDate=start, timeUnit=time_unit, periods=3)) == expected


@pytest.mark.parametrize(
    ("time_unit", "start", "rule"),
    [
        ("week", "2026-12-29", "a Monday"),
        ("month", "2026-11-02", "the 1st of a month"),
        ("year", "2027-02-01", "1 January"),
    ],
)
def test_unaligned_start_date_is_rejected(
    time_unit: TimeserieTimeUnit,
    start: str,
    rule: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        _spec(startDate=start, timeUnit=time_unit)

    assert f"startDate {start} is not a valid {time_unit} start date" in str(
        error.value
    )
    assert rule in str(error.value)


def test_unaligned_level_shift_date_is_rejected() -> None:
    with pytest.raises(ValidationError, match="levelShifts date 2026-03-15"):
        _spec(levelShifts=[{"date": "2026-03-15", "delta": 1}])


def test_no_trend_keeps_base_level() -> None:
    assert _values(_spec(periods=3)) == [100.0, 100.0, 100.0]


def test_linear_trend_adds_slope_per_period() -> None:
    values = _values(_spec(periods=4, trend={"type": "linear", "slope": -2.5}))

    assert values == [100.0, 97.5, 95.0, 92.5]


def test_percent_trend_compounds() -> None:
    values = _values(
        _spec(periods=3, trend={"type": "percent", "percentPerPeriod": 10})
    )

    assert values == [100.0, 110.0, 121.0]


def test_logistic_trend_moves_from_base_level_to_capacity() -> None:
    values = _values(
        _spec(
            periods=41,
            trend={
                "type": "logistic",
                "capacity": 500,
                "growthRate": 0.5,
                "midpoint": 20,
            },
        )
    )

    assert values[20] == 300.0
    assert values[0] == pytest.approx(100, abs=0.02)
    assert values[-1] == pytest.approx(500, abs=0.02)
    assert values == sorted(values)


def test_additive_seasonality_peaks_at_offset() -> None:
    values = _values(
        _spec(
            periods=24,
            seasonality=[
                {"period": 12, "amplitude": 10, "mode": "additive", "peakOffset": 11}
            ],
        )
    )

    assert values[11] == 110.0
    assert values[23] == 110.0
    assert values[5] == 90.0
    assert max(values) == 110.0
    assert sum(values[:12]) == pytest.approx(1200)


def test_multiplicative_seasonality_scales_with_level() -> None:
    values = _values(
        _spec(
            periods=4,
            trend={"type": "linear", "slope": 100},
            seasonality=[{"period": 2, "amplitude": 0.5, "mode": "multiplicative"}],
        )
    )

    assert values == [150.0, 100.0, 450.0, 200.0]


def test_std_noise_has_requested_spread_and_zero_mean() -> None:
    values = np.array(
        _values(_spec(timeUnit="day", periods=20_000, noise={"std": 4}, seed=7))
    )
    noise = values - 100

    assert noise.std() == pytest.approx(4, rel=0.05)
    assert noise.mean() == pytest.approx(0, abs=0.2)


def test_relative_noise_scales_with_level() -> None:
    low = np.array(
        _values(
            _spec(
                timeUnit="day",
                periods=5_000,
                baseLevel=10,
                noise={"relativeStd": 0.1},
            )
        )
    )
    high = np.array(
        _values(
            _spec(
                timeUnit="day",
                periods=5_000,
                baseLevel=1_000,
                noise={"relativeStd": 0.1},
            )
        )
    )

    assert low.std() == pytest.approx(1, rel=0.1)
    assert high.std() == pytest.approx(100, rel=0.1)


def test_ar1_noise_is_autocorrelated_and_keeps_its_std() -> None:
    values = np.array(
        _values(
            _spec(
                timeUnit="day",
                periods=20_000,
                baseLevel=0,
                noise={"std": 2, "ar1": 0.8},
            )
        )
    )
    lag_one = float(np.corrcoef(values[:-1], values[1:])[0, 1])

    assert lag_one == pytest.approx(0.8, abs=0.03)
    assert values.std() == pytest.approx(2, rel=0.1)


@pytest.mark.parametrize("noise", [{}, {"std": 1, "relativeStd": 0.1}])
def test_noise_needs_exactly_one_scale(noise: dict[str, float]) -> None:
    with pytest.raises(ValidationError, match="exactly one of std or relativeStd"):
        _spec(noise=noise)


def test_level_shifts_apply_from_their_date_and_accumulate() -> None:
    values = _values(
        _spec(
            periods=5,
            levelShifts=[
                {"date": "2026-02-01", "delta": 10},
                {"date": "2026-04-01", "delta": -30},
            ],
        )
    )

    assert values == [100.0, 110.0, 110.0, 80.0, 80.0]


def test_clamp_limits_values() -> None:
    values = _values(
        _spec(
            periods=5,
            trend={"type": "linear", "slope": -40},
            clampMin=0,
            clampMax=90,
        )
    )

    assert values == [90.0, 60.0, 20.0, 0.0, 0.0]


def test_clamp_min_must_not_exceed_clamp_max() -> None:
    with pytest.raises(ValidationError, match="clampMin must not be greater"):
        _spec(clampMin=10, clampMax=5)


def test_values_are_rounded_to_decimals_without_negative_zero() -> None:
    rounded = _values(
        _spec(periods=3, baseLevel=0.0001, trend={"type": "linear", "slope": 1.23456})
    )
    whole = _values(
        _spec(
            periods=2,
            baseLevel=-0.2,
            trend={"type": "linear", "slope": 2.6},
            decimals=0,
        )
    )

    assert _values(_spec(periods=1, baseLevel=1.23456, decimals=3)) == [1.235]
    assert rounded == [0.0001, 1.23466, 2.46922]
    assert whole == [0.0, 2.0]
    assert math.copysign(1, whole[0]) == 1


def test_point_limit_is_enforced_for_periods() -> None:
    assert len(generate(_spec(timeUnit="day", periods=MAX_GENERATED_POINTS))) == (
        MAX_GENERATED_POINTS
    )
    with pytest.raises(ValidationError, match="less than or equal to 20000"):
        _spec(timeUnit="day", periods=MAX_GENERATED_POINTS + 1)


def test_point_limit_is_enforced_for_end_date() -> None:
    with pytest.raises(ValidationError, match="produces 20001 points"):
        _spec(
            timeUnit="day",
            periods=None,
            startDate="2000-01-01",
            endDate=date.fromordinal(date(2000, 1, 1).toordinal() + 20_000).isoformat(),
        )


def test_point_limit_can_be_reached_with_end_date() -> None:
    spec = _spec(
        timeUnit="day",
        periods=None,
        startDate="2000-01-01",
        endDate=date.fromordinal(date(2000, 1, 1).toordinal() + 19_999).isoformat(),
    )

    assert len(generate(spec)) == MAX_GENERATED_POINTS


@pytest.mark.parametrize(
    ("time_unit", "start", "fitting_periods"),
    [
        ("day", "9999-12-01", 31),
        ("week", "9999-12-13", 3),
        ("month", "9999-11-01", 2),
        ("year", "9990-01-01", 10),
    ],
)
def test_dates_past_the_largest_date_are_rejected(
    time_unit: TimeserieTimeUnit,
    start: str,
    fitting_periods: int,
) -> None:
    last = _dates(_spec(timeUnit=time_unit, startDate=start, periods=fitting_periods))

    assert last[-1].year == 9999
    with pytest.raises(ValidationError, match="past the largest supported date"):
        _spec(timeUnit=time_unit, startDate=start, periods=fitting_periods + 1)


@pytest.mark.parametrize(
    ("time_unit", "start", "end", "expected_periods", "last_date"),
    [
        ("day", "2026-02-27", "2026-03-02", 4, date(2026, 3, 2)),
        ("week", "2026-01-05", "2026-01-25", 3, date(2026, 1, 19)),
        ("week", "2026-01-05", "2026-01-26", 4, date(2026, 1, 26)),
        ("month", "2026-01-01", "2026-12-15", 12, date(2026, 12, 1)),
        ("month", "2026-11-01", "2027-02-28", 4, date(2027, 2, 1)),
        ("year", "2026-01-01", "2028-06-30", 3, date(2028, 1, 1)),
        ("year", "2026-01-01", "2026-01-01", 1, date(2026, 1, 1)),
    ],
)
def test_end_date_is_inclusive_and_matches_periods(
    time_unit: TimeserieTimeUnit,
    start: str,
    end: str,
    expected_periods: int,
    last_date: date,
) -> None:
    by_end_date = _spec(timeUnit=time_unit, startDate=start, periods=None, endDate=end)
    by_periods = _spec(timeUnit=time_unit, startDate=start, periods=expected_periods)

    assert by_end_date.point_count() == expected_periods
    assert generate(by_end_date) == generate(by_periods)
    assert _dates(by_end_date)[-1] == last_date


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"periods": 3, "endDate": "2026-12-01"}, "exactly one of periods or endDate"),
        ({"periods": None}, "exactly one of periods or endDate"),
        ({"periods": None, "endDate": "2025-12-31"}, "must not be before startDate"),
    ],
)
def test_periods_and_end_date_are_exclusive(
    overrides: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _spec(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"seasonality": [{"period": 12, "amplitude": 1.5, "mode": "multiplicative"}]},
        {"trend": {"type": "percent", "percentPerPeriod": -100}},
        {"trend": {"type": "logistic", "capacity": 1, "growthRate": 0, "midpoint": 1}},
        {"noise": {"std": 1, "ar1": 1}},
        {"baseLevel": float("inf")},
        {"unknownField": 1},
    ],
)
def test_invalid_parameters_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        _spec(**overrides)


def test_non_finite_output_is_rejected() -> None:
    spec = _spec(
        timeUnit="day",
        periods=20_000,
        trend={"type": "percent", "percentPerPeriod": 1_000},
    )

    with pytest.raises(TimeserieGenerationError, match="not finite"):
        generate(spec)


def test_rounding_overflow_is_rejected_as_non_finite() -> None:
    spec = _spec(periods=1, baseLevel=1e300, decimals=10)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(TimeserieGenerationError, match="not finite"):
            generate(spec)
    assert _values(_spec(periods=1, baseLevel=1e300, decimals=2)) == [1e300]


def test_percent_trend_with_zero_base_level_stays_zero() -> None:
    values = _values(
        _spec(
            timeUnit="day",
            periods=20_000,
            baseLevel=0,
            trend={"type": "percent", "percentPerPeriod": 1_000},
        )
    )

    assert values == [0.0] * 20_000


@pytest.mark.parametrize(
    "overrides",
    [
        {"seed": True},
        {"seed": "1"},
        {"decimals": True},
        {"periods": "3"},
        {"periods": 3.0},
        {"baseLevel": "1e2"},
        {"baseLevel": False},
        {"noise": {"std": "1"}},
        {"trend": {"type": "linear", "slope": True}},
        {"seasonality": [{"period": "12", "amplitude": 1, "mode": "additive"}]},
    ],
)
def test_numeric_fields_are_not_coerced(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Input should be a valid"):
        _spec(**overrides)


def test_json_spec_accepts_integers_for_number_fields() -> None:
    spec = TimeserieGenerationSpec.model_validate_json(
        '{"startDate": "2026-01-05", "periods": 2, "timeUnit": "week", '
        '"baseLevel": 10, "trend": {"type": "linear", "slope": 2}, "seed": 3}'
    )

    assert _values(spec) == [10.0, 12.0]


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with factory() as session:
        session.add(
            User(
                user_id=ACTOR_USER_ID,
                name="Test Admin",
                email="test-admin@example.test",
                role="admin",
            ),
        )
        session.add(Metamodel(version=1))
        session.commit()

    yield factory


@pytest.mark.parametrize(
    ("time_unit", "start"),
    [
        ("day", "2026-01-30"),
        ("week", "2026-01-05"),
        ("month", "2026-01-01"),
        ("year", "2026-01-01"),
    ],
)
def test_generated_values_pass_existing_timeserie_value_validation(
    session_factory: sessionmaker[Session],
    time_unit: TimeserieTimeUnit,
    start: str,
) -> None:
    spec = _spec(
        startDate=start,
        timeUnit=time_unit,
        periods=60,
        trend={"type": "linear", "slope": 1.5},
        seasonality=[{"period": 12, "amplitude": 0.1, "mode": "multiplicative"}],
        noise={"relativeStd": 0.05},
        decimals=2,
    )
    points = generate(spec)

    with session_factory() as session:
        organisation = organisations_service.create_organisation(
            session,
            OrganisationCreateRequest(name="Acme Corp"),
            ACTOR_USER_ID,
        )
        scenario = org_states_service.create_scenario_in_transaction(
            session,
            organisation.id,
            ScenarioCreateRequest(name="Generated"),
            ACTOR_USER_ID,
        )
        org_states_service.create_timeserie_in_transaction(
            session,
            organisation.id,
            scenario.scenario_key,
            TimeserieCreateRequest(
                id="revenue",
                name="Revenue",
                timeUnit=time_unit,
                valueUnit="number",
            ),
            ACTOR_USER_ID,
        )
        timeserie = org_states_service.replace_timeserie_values_in_transaction(
            session,
            organisation.id,
            scenario.scenario_key,
            "revenue",
            TimeserieValuesPatchRequest.model_validate(
                {"values": [point.model_dump(mode="json") for point in points]}
            ),
            ACTOR_USER_ID,
        )
        stored = session.scalars(
            select(TimeserieValue)
            .where(TimeserieValue.timeserie_id == timeserie.timeserie_id)
            .order_by(TimeserieValue.date)
        ).all()

    assert [(value.date, value.value["value"]) for value in stored] == [
        (point.date, point.value) for point in points
    ]
