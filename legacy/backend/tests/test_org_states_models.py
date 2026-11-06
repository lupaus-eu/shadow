from app.api.v1.org_states.models import Event, OrgState


def test_scenario_target_dates_are_non_nullable_in_orm_metadata() -> None:
    assert OrgState.__table__.columns["target_date"].nullable is False
    assert Event.__table__.columns["target_date"].nullable is False
