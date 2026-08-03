import logging
import math
from datetime import UTC, datetime
from datetime import date as dt_date
from typing import cast
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.org_states.models import (
    Event,
    OrgState,
    Scenario,
    Timeserie,
    TimeserieValue,
)
from app.api.v1.org_states.schemas import (
    EventCreateRequest,
    EventPatchRequest,
    EventResponse,
    OrgStateCreateRequest,
    OrgStatePatchRequest,
    OrgStateResponse,
    ScenarioCopyRequest,
    ScenarioCreateRequest,
    ScenarioPatchRequest,
    ScenarioResponse,
    TimeserieCellValue,
    TimeserieCreateRequest,
    TimeserieExistsResponse,
    TimeserieResponse,
    TimeserieTimeUnit,
    TimeserieValueResponse,
    TimeserieValuesPatchRequest,
    TimeserieValueUnit,
)
from app.api.v1.org_twin_structure import org_twin_structure_service
from app.api.v1.organisations.models import Organisation

DEFAULT_SCENARIO_NAME = "Reality"
DEFAULT_SCENARIO_DESCRIPTION = "The reality of the organisation"
DEFAULT_SCENARIO_PROTECTED = True
DEFAULT_ORG_STATE_NAME = "Initial state"
DEFAULT_ORG_STATE_DESCRIPTION = "Initial state of reality"
DEFAULT_ORG_STATE_TARGET_DATE = dt_date(2020, 1, 1)
logger = logging.getLogger(__name__)


def create_default_scenario(session: Session, organisation: Organisation) -> Scenario:
    scenario = Scenario(
        organisation_id=organisation.organisation_id,
        scenario_key="reality",
        name=DEFAULT_SCENARIO_NAME,
        description=DEFAULT_SCENARIO_DESCRIPTION,
        protected=DEFAULT_SCENARIO_PROTECTED,
    )
    session.add(scenario)
    session.flush()
    return scenario


def create_default_org_state(session: Session, scenario: Scenario) -> OrgState:
    org_state = OrgState(
        scenario_id=scenario.scenario_id,
        org_state_key="initial_state",
        name=DEFAULT_ORG_STATE_NAME,
        description=DEFAULT_ORG_STATE_DESCRIPTION,
        target_date=DEFAULT_ORG_STATE_TARGET_DATE,
    )
    session.add(org_state)
    session.flush()
    return org_state


def link_initial_state(scenario: Scenario, org_state: OrgState) -> None:
    scenario.initial_state_id = org_state.org_state_id


def list_scenarios(
    session: Session,
    organisation: Organisation,
) -> list[ScenarioResponse]:
    scenarios = session.scalars(
        select(Scenario)
        .where(
            Scenario.organisation_id == organisation.organisation_id,
            Scenario.deleted_time.is_(None),
        )
        .order_by(Scenario.name, Scenario.scenario_id),
    ).all()

    return [to_scenario_response(scenario) for scenario in scenarios]


def list_organisation_scenarios(
    session: Session,
    organisation_key: str,
) -> list[ScenarioResponse]:
    organisation = _get_active_organisation(session, organisation_key)
    return list_scenarios(session, organisation)


def get_scenario(
    session: Session,
    organisation_key: str,
    scenario_key: str,
) -> ScenarioResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    return to_scenario_response(scenario)


def create_scenario(
    session: Session,
    organisation_key: str,
    payload: ScenarioCreateRequest,
) -> ScenarioResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = Scenario(
        organisation_id=organisation.organisation_id,
        scenario_key=_generate_scenario_key(),
        name=payload.name,
        description=payload.description,
        protected=False,
    )
    session.add(scenario)
    session.commit()
    session.refresh(scenario)

    return to_scenario_response(scenario)


def copy_scenario(
    session: Session,
    organisation_key: str,
    payload: ScenarioCopyRequest,
) -> ScenarioResponse:
    organisation = _get_active_organisation(session, organisation_key)
    source_scenario = _get_active_scenario(
        session,
        organisation,
        payload.source_scenario_id,
    )
    source_org_state = _get_active_org_state(
        session,
        source_scenario,
        payload.source_org_state_id,
    )

    copied_scenario = Scenario(
        organisation_id=organisation.organisation_id,
        scenario_key=_generate_scenario_key(),
        name=payload.name or f"Fork of {source_scenario.name}",
        description=payload.description,
        protected=False,
        source_scenario_id=source_scenario.scenario_id,
    )
    session.add(copied_scenario)
    session.flush()

    copied_org_state = OrgState(
        scenario_id=copied_scenario.scenario_id,
        org_state_key=_generate_org_state_key(),
        name=source_org_state.name,
        version=source_org_state.version,
        description=source_org_state.description,
        target_date=source_org_state.target_date,
    )
    session.add(copied_org_state)
    session.flush()
    copied_scenario.initial_state_id = copied_org_state.org_state_id

    org_twin_structure_service.copy_graph_snapshots_for_org_states(
        session,
        {source_org_state.org_state_id: copied_org_state.org_state_id},
    )

    session.commit()
    session.refresh(copied_scenario)

    return to_scenario_response(copied_scenario)


def patch_scenario(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    payload: ScenarioPatchRequest,
) -> ScenarioResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)

    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data and payload.name is not None:
        scenario.name = payload.name
    if "description" in update_data:
        scenario.description = payload.description

    scenario.modified_time = datetime.now(UTC)
    session.commit()
    session.refresh(scenario)

    return to_scenario_response(scenario)


def soft_delete_scenario(
    session: Session,
    organisation_key: str,
    scenario_key: str,
) -> None:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    _ensure_scenario_allows_destructive_action(scenario)

    now = datetime.now(UTC)
    active_org_states = session.scalars(
        select(OrgState).where(
            OrgState.scenario_id == scenario.scenario_id,
            OrgState.deleted_time.is_(None),
        ),
    ).all()

    _soft_delete_timeseries(session, scenario, now)
    _soft_delete_events(session, scenario, now)
    org_twin_structure_service.soft_delete_graph_structure_for_scenario(
        session,
        scenario.scenario_id,
        now,
    )

    for org_state in active_org_states:
        org_state.deleted_time = now
        org_state.modified_time = now

    scenario.deleted_time = now
    scenario.modified_time = now
    session.commit()


def list_org_states(
    session: Session,
    organisation: Organisation,
    scenario_key: str,
) -> list[OrgStateResponse]:
    scenario = _get_active_scenario(session, organisation, scenario_key)
    org_states = session.scalars(
        select(OrgState)
        .where(
            OrgState.scenario_id == scenario.scenario_id,
            OrgState.deleted_time.is_(None),
        )
        .order_by(OrgState.target_date, OrgState.org_state_id),
    ).all()

    return [to_org_state_response(org_state) for org_state in org_states]


def list_organisation_scenario_org_states(
    session: Session,
    organisation_key: str,
    scenario_key: str,
) -> list[OrgStateResponse]:
    organisation = _get_active_organisation(session, organisation_key)
    return list_org_states(session, organisation, scenario_key)


def clean_org_states(
    session: Session,
    organisation_key: str,
    scenario_key: str,
) -> int:
    try:
        organisation = _get_active_organisation(session, organisation_key)
        scenario = _get_active_scenario(
            session,
            organisation,
            scenario_key,
            for_update=True,
        )
        _ensure_scenario_allows_destructive_action(scenario)

        now = datetime.now(UTC)
        active_org_states = session.scalars(
            select(OrgState).where(
                OrgState.scenario_id == scenario.scenario_id,
                OrgState.deleted_time.is_(None),
            ),
        ).all()
        cleaned_org_state_ids = [
            org_state.org_state_id for org_state in active_org_states
        ]

        if scenario.initial_state_id in cleaned_org_state_ids:
            scenario.initial_state_id = None
            scenario.modified_time = now

        org_twin_structure_service.soft_delete_graphs_for_org_states(
            session,
            cleaned_org_state_ids,
            now,
        )

        for org_state in active_org_states:
            org_state.deleted_time = now
            org_state.modified_time = now

        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        logger.exception(
            "Failed to clean organisation states for organisation_key=%s "
            "scenario_key=%s",
            organisation_key,
            scenario_key,
        )
        raise

    cleaned_count = len(active_org_states)
    logger.info(
        "Cleaned %s organisation states for organisation_key=%s scenario_key=%s",
        cleaned_count,
        organisation_key,
        scenario_key,
    )
    return cleaned_count


def get_org_state(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
) -> OrgStateResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    org_state = _get_active_org_state(session, scenario, org_state_key)
    return to_org_state_response(org_state)


def create_org_state(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    payload: OrgStateCreateRequest,
) -> OrgStateResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(
        session,
        organisation,
        scenario_key,
        for_update=True,
    )
    _ensure_target_date_is_available(session, scenario, payload.target_date)

    org_state = OrgState(
        scenario_id=scenario.scenario_id,
        org_state_key=_generate_org_state_key(),
        name=payload.name,
        description=payload.description,
        target_date=payload.target_date,
    )
    session.add(org_state)
    session.commit()
    session.refresh(org_state)

    return to_org_state_response(org_state)


def patch_org_state(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    payload: OrgStatePatchRequest,
) -> OrgStateResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(
        session,
        organisation,
        scenario_key,
        for_update=True,
    )
    org_state = _get_active_org_state(session, scenario, org_state_key)
    update_data = payload.model_dump(exclude_unset=True, by_alias=False)

    if "target_date" in update_data:
        if payload.target_date is None:
            raise HTTPException(
                status_code=422,
                detail="Organisation state target date is required.",
            )
        _ensure_target_date_is_available(
            session,
            scenario,
            payload.target_date,
            excluding_org_state_id=org_state.org_state_id,
        )
        org_state.target_date = payload.target_date
    if "name" in update_data and payload.name is not None:
        org_state.name = payload.name
    if "description" in update_data:
        org_state.description = payload.description

    org_state.modified_time = datetime.now(UTC)
    session.commit()
    session.refresh(org_state)

    return to_org_state_response(org_state)


def soft_delete_org_state(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
) -> None:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    org_state = _get_active_org_state(session, scenario, org_state_key)
    now = datetime.now(UTC)

    if scenario.initial_state_id == org_state.org_state_id:
        scenario.initial_state_id = None
        scenario.modified_time = now

    org_twin_structure_service.soft_delete_graphs_for_org_states(
        session,
        [org_state.org_state_id],
        now,
    )
    org_state.deleted_time = now
    org_state.modified_time = now
    session.commit()


def list_scenario_events(
    session: Session,
    organisation_key: str,
    scenario_key: str,
) -> list[EventResponse]:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    events = session.scalars(
        select(Event)
        .where(
            Event.scenario_id == scenario.scenario_id,
            Event.deleted_time.is_(None),
        )
        .order_by(Event.target_date, Event.event_id),
    ).all()

    return [to_event_response(event) for event in events]


def get_event(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    event_key: str,
) -> EventResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    event = _get_active_event(session, scenario, event_key)
    return to_event_response(event)


def create_event(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    payload: EventCreateRequest,
) -> EventResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)

    event = Event(
        scenario_id=scenario.scenario_id,
        event_key=_generate_event_key(),
        name=payload.name,
        target_date=payload.target_date,
        event_details=payload.event_details,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    return to_event_response(event)


def patch_event(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    event_key: str,
    payload: EventPatchRequest,
) -> EventResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    event = _get_active_event(session, scenario, event_key)
    update_data = payload.model_dump(exclude_unset=True, by_alias=False)

    if "target_date" in update_data:
        if payload.target_date is None:
            raise HTTPException(
                status_code=422,
                detail="Event target date is required.",
            )
        event.target_date = payload.target_date
    if "name" in update_data and payload.name is not None:
        event.name = payload.name
    if "event_details" in update_data:
        event.event_details = payload.event_details

    event.modified_time = datetime.now(UTC)
    session.commit()
    session.refresh(event)

    return to_event_response(event)


def soft_delete_event(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    event_key: str,
) -> None:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    event = _get_active_event(session, scenario, event_key)
    now = datetime.now(UTC)

    event.deleted_time = now
    event.modified_time = now
    session.commit()


def get_timeserie(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
) -> TimeserieResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    timeserie = _get_active_timeserie(
        session,
        scenario,
        _normalise_stable_key(timeserie_key, "Timeserie id must not be blank."),
    )

    values = _active_timeserie_values(session, timeserie)
    return to_timeserie_response(timeserie, values)


def list_scenario_timeseries(
    session: Session,
    organisation_key: str,
    scenario_key: str,
) -> list[TimeserieResponse]:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    timeseries = session.scalars(
        select(Timeserie)
        .where(
            Timeserie.scenario_id == scenario.scenario_id,
            Timeserie.deleted_time.is_(None),
        )
        .order_by(Timeserie.timeserie_key, Timeserie.timeserie_id),
    ).all()
    values_by_timeserie_id = _active_values_by_timeserie_id(
        session,
        [timeserie.timeserie_id for timeserie in timeseries],
    )

    return [
        to_timeserie_response(
            timeserie,
            values_by_timeserie_id.get(timeserie.timeserie_id, []),
        )
        for timeserie in timeseries
    ]


def timeserie_exists(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
) -> TimeserieExistsResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    normalised_key = _normalise_stable_key(
        timeserie_key,
        "Timeserie id must not be blank.",
    )

    timeserie_id = session.scalar(
        select(Timeserie.timeserie_id).where(
            Timeserie.scenario_id == scenario.scenario_id,
            Timeserie.timeserie_key == normalised_key,
            Timeserie.deleted_time.is_(None),
        ),
    )

    return TimeserieExistsResponse(id=normalised_key, exists=timeserie_id is not None)


def create_timeserie(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    payload: TimeserieCreateRequest,
) -> TimeserieResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    _ensure_timeserie_key_available(session, scenario, payload.id)

    timeserie = Timeserie(
        scenario_id=scenario.scenario_id,
        timeserie_key=payload.id,
        name=payload.name,
        description=payload.description,
        unit=payload.unit,
        time_unit=payload.time_unit,
        value_unit=payload.value_unit,
    )
    session.add(timeserie)
    session.commit()
    session.refresh(timeserie)

    return to_timeserie_response(timeserie)


def replace_timeserie_values(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
    payload: TimeserieValuesPatchRequest,
) -> TimeserieResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    timeserie = _get_active_timeserie(
        session,
        scenario,
        _normalise_stable_key(timeserie_key, "Timeserie id must not be blank."),
        for_update=True,
    )

    replacement_values: dict[dt_date, TimeserieCellValue] = {}
    time_unit = cast(TimeserieTimeUnit, timeserie.time_unit)
    value_unit = cast(TimeserieValueUnit, timeserie.value_unit)
    for item in payload.values:
        _ensure_timeserie_value_date_is_valid(time_unit, item.date)
        replacement_values[item.date] = _normalise_timeserie_cell_value(
            value_unit,
            item.value,
        )

    now = datetime.now(UTC)
    existing_values = session.scalars(
        select(TimeserieValue)
        .where(TimeserieValue.timeserie_id == timeserie.timeserie_id)
        .with_for_update(),
    ).all()
    existing_by_date = {value.date: value for value in existing_values}

    for value in existing_values:
        if value.deleted_time is None and value.date not in replacement_values:
            value.deleted_time = now
            value.modified_time = now

    for value_date, cell_value in replacement_values.items():
        stored_value: dict[str, object] = {"value": cell_value}
        existing_value = existing_by_date.get(value_date)
        if existing_value is None:
            session.add(
                TimeserieValue(
                    timeserie_id=timeserie.timeserie_id,
                    date=value_date,
                    value=stored_value,
                ),
            )
            continue

        existing_value.value = stored_value
        existing_value.deleted_time = None
        existing_value.modified_time = now

    timeserie.modified_time = now
    session.commit()
    session.refresh(timeserie)

    values = _active_timeserie_values(session, timeserie)
    return to_timeserie_response(timeserie, values)


def soft_delete_timeserie(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
) -> None:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    timeserie = _get_active_timeserie(
        session,
        scenario,
        _normalise_stable_key(timeserie_key, "Timeserie id must not be blank."),
    )
    now = datetime.now(UTC)

    org_twin_structure_service.clear_timeserie_references(
        session,
        scenario.scenario_id,
        timeserie.timeserie_id,
        now,
    )
    _soft_delete_timeserie_values(session, timeserie, now)
    timeserie.deleted_time = now
    timeserie.modified_time = now
    session.commit()


def to_scenario_response(scenario: Scenario) -> ScenarioResponse:
    return ScenarioResponse(
        id=scenario.scenario_key,
        name=scenario.name,
        description=scenario.description or "",
        protected=scenario.protected,
    )


def to_org_state_response(org_state: OrgState) -> OrgStateResponse:
    return OrgStateResponse(
        id=org_state.org_state_key,
        name=org_state.name,
        description=org_state.description or "",
        targetDate=org_state.target_date,
    )


def to_event_response(event: Event) -> EventResponse:
    return EventResponse(
        id=event.event_key,
        name=event.name,
        targetDate=event.target_date,
        eventDetails=event.event_details or "",
    )


def to_timeserie_response(
    timeserie: Timeserie,
    values: list[TimeserieValue] | None = None,
) -> TimeserieResponse:
    return TimeserieResponse(
        id=timeserie.timeserie_key,
        name=timeserie.name,
        description=timeserie.description or "",
        unit=timeserie.unit or "",
        timeUnit=cast(TimeserieTimeUnit, timeserie.time_unit),
        valueUnit=cast(TimeserieValueUnit, timeserie.value_unit),
        values=[
            TimeserieValueResponse(
                date=value.date,
                value=_timeserie_cell_value_from_storage(value.value),
            )
            for value in (values or [])
        ],
    )


def _get_active_organisation(session: Session, organisation_key: str) -> Organisation:
    from app.api.v1.organisations.service import get_active_organisation

    return get_active_organisation(session, organisation_key)


def _get_active_scenario(
    session: Session,
    organisation: Organisation,
    scenario_key: str,
    *,
    for_update: bool = False,
) -> Scenario:
    query = select(Scenario).where(
        Scenario.organisation_id == organisation.organisation_id,
        Scenario.scenario_key == scenario_key,
        Scenario.deleted_time.is_(None),
    )
    if for_update:
        query = query.with_for_update()

    scenario = session.scalar(query)

    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found.",
        )

    return scenario


def _get_active_org_state(
    session: Session,
    scenario: Scenario,
    org_state_key: str,
) -> OrgState:
    org_state = session.scalar(
        select(OrgState).where(
            OrgState.scenario_id == scenario.scenario_id,
            OrgState.org_state_key == org_state_key,
            OrgState.deleted_time.is_(None),
        ),
    )

    if org_state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisation state not found.",
        )

    return org_state


def _get_active_event(
    session: Session,
    scenario: Scenario,
    event_key: str,
) -> Event:
    event = session.scalar(
        select(Event).where(
            Event.scenario_id == scenario.scenario_id,
            Event.event_key == event_key,
            Event.deleted_time.is_(None),
        ),
    )

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found.",
        )

    return event


def _get_active_timeserie(
    session: Session,
    scenario: Scenario,
    timeserie_key: str,
    *,
    for_update: bool = False,
) -> Timeserie:
    query = select(Timeserie).where(
        Timeserie.scenario_id == scenario.scenario_id,
        Timeserie.timeserie_key == timeserie_key,
        Timeserie.deleted_time.is_(None),
    )
    if for_update:
        query = query.with_for_update()

    timeserie = session.scalar(query)

    if timeserie is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Timeserie not found.",
        )

    return timeserie


def _active_timeserie_values(
    session: Session,
    timeserie: Timeserie,
) -> list[TimeserieValue]:
    return list(
        session.scalars(
            select(TimeserieValue)
            .where(
                TimeserieValue.timeserie_id == timeserie.timeserie_id,
                TimeserieValue.deleted_time.is_(None),
            )
            .order_by(TimeserieValue.date, TimeserieValue.timeserie_value_id),
        ).all(),
    )


def _active_values_by_timeserie_id(
    session: Session,
    timeserie_ids: list[int],
) -> dict[int, list[TimeserieValue]]:
    if not timeserie_ids:
        return {}

    values = session.scalars(
        select(TimeserieValue)
        .where(
            TimeserieValue.timeserie_id.in_(timeserie_ids),
            TimeserieValue.deleted_time.is_(None),
        )
        .order_by(
            TimeserieValue.timeserie_id,
            TimeserieValue.date,
            TimeserieValue.timeserie_value_id,
        ),
    ).all()
    values_by_timeserie_id: dict[int, list[TimeserieValue]] = {
        timeserie_id: [] for timeserie_id in timeserie_ids
    }
    for value in values:
        values_by_timeserie_id.setdefault(value.timeserie_id, []).append(value)

    return values_by_timeserie_id


def _ensure_timeserie_value_date_is_valid(
    time_unit: TimeserieTimeUnit,
    value_date: dt_date,
) -> None:
    if time_unit == "day":
        return

    valid = (
        value_date.weekday() == 0
        if time_unit == "week"
        else value_date.day == 1
        if time_unit == "month"
        else value_date.month == 1 and value_date.day == 1
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{value_date.isoformat()} is not a valid {time_unit} start date.",
        )


def _normalise_timeserie_cell_value(
    value_unit: TimeserieValueUnit,
    value: TimeserieCellValue,
) -> TimeserieCellValue:
    if value_unit == "number":
        is_finite_number = False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                is_finite_number = math.isfinite(float(value))
            except OverflowError:
                is_finite_number = False

        if not is_finite_number:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Timeserie value must be a finite number.",
            )
        return value

    if value_unit == "string":
        if not isinstance(value, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Timeserie value must be a string.",
            )
        return value

    if not isinstance(value, bool):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Timeserie value must be a boolean.",
        )

    return value


def _timeserie_cell_value_from_storage(
    stored_value: dict[str, object],
) -> TimeserieCellValue:
    raw_value = stored_value.get("value")
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return raw_value
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float) and math.isfinite(raw_value):
        return raw_value

    return ""


def _soft_delete_events(
    session: Session,
    scenario: Scenario,
    deleted_time: datetime,
) -> None:
    events = session.scalars(
        select(Event).where(
            Event.scenario_id == scenario.scenario_id,
            Event.deleted_time.is_(None),
        ),
    ).all()

    for event in events:
        event.deleted_time = deleted_time
        event.modified_time = deleted_time


def _soft_delete_timeseries(
    session: Session,
    scenario: Scenario,
    deleted_time: datetime,
) -> None:
    timeseries = session.scalars(
        select(Timeserie).where(
            Timeserie.scenario_id == scenario.scenario_id,
            Timeserie.deleted_time.is_(None),
        ),
    ).all()
    timeserie_ids = [timeserie.timeserie_id for timeserie in timeseries]

    if timeserie_ids:
        values = session.scalars(
            select(TimeserieValue).where(
                TimeserieValue.timeserie_id.in_(timeserie_ids),
                TimeserieValue.deleted_time.is_(None),
            ),
        ).all()

        for value in values:
            value.deleted_time = deleted_time
            value.modified_time = deleted_time

    for timeserie in timeseries:
        timeserie.deleted_time = deleted_time
        timeserie.modified_time = deleted_time


def _soft_delete_timeserie_values(
    session: Session,
    timeserie: Timeserie,
    deleted_time: datetime,
) -> None:
    values = session.scalars(
        select(TimeserieValue).where(
            TimeserieValue.timeserie_id == timeserie.timeserie_id,
            TimeserieValue.deleted_time.is_(None),
        ),
    ).all()

    for value in values:
        value.deleted_time = deleted_time
        value.modified_time = deleted_time


def _ensure_target_date_is_available(
    session: Session,
    scenario: Scenario,
    target_date: dt_date | None,
    excluding_org_state_id: int | None = None,
) -> None:
    if target_date is None:
        return

    query = select(OrgState.org_state_id).where(
        OrgState.scenario_id == scenario.scenario_id,
        OrgState.target_date == target_date,
        OrgState.deleted_time.is_(None),
    )

    if excluding_org_state_id is not None:
        query = query.where(OrgState.org_state_id != excluding_org_state_id)

    if session.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active organisation state with this target date already exists.",
        )


def _ensure_timeserie_key_available(
    session: Session,
    scenario: Scenario,
    timeserie_key: str,
) -> None:
    timeserie_id = session.scalar(
        select(Timeserie.timeserie_id).where(
            Timeserie.scenario_id == scenario.scenario_id,
            Timeserie.timeserie_key == timeserie_key,
            Timeserie.deleted_time.is_(None),
        ),
    )
    if timeserie_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active timeserie with this id already exists.",
        )


def _ensure_scenario_allows_destructive_action(scenario: Scenario) -> None:
    if scenario.protected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Protected scenarios cannot be deleted or cleaned.",
        )


def _normalise_stable_key(value: str, blank_message: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=blank_message,
        )
    return stripped


def _generate_scenario_key() -> str:
    return f"scenario_{uuid4().hex}"


def _generate_org_state_key() -> str:
    return f"org_state_{uuid4().hex}"


def _generate_event_key() -> str:
    return f"event_{uuid4().hex}"
