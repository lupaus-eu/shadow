import logging
import math
from copy import deepcopy
from datetime import UTC, datetime
from datetime import date as dt_date
from typing import cast
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.org_states.derived_metrics import (
    FormulaError,
    ParsedFormula,
    evaluate_formula,
    parse_formula,
)
from app.api.v1.org_states.models import (
    DerivedMetricEquation,
    Event,
    OrgState,
    Scenario,
    Timeserie,
    TimeserieValue,
)
from app.api.v1.org_states.schemas import (
    DerivedMetricCreateRequest,
    DerivedMetricPatchRequest,
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
    TimeserieShortNamePatchRequest,
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


def create_default_scenario(
    session: Session, organisation: Organisation, actor_user_id: int
) -> Scenario:
    scenario = Scenario(
        organisation_id=organisation.organisation_id,
        scenario_key="reality",
        name=DEFAULT_SCENARIO_NAME,
        description=DEFAULT_SCENARIO_DESCRIPTION,
        protected=DEFAULT_SCENARIO_PROTECTED,
        created_by=actor_user_id,
    )
    session.add(scenario)
    session.flush()
    return scenario


def create_default_org_state(
    session: Session, scenario: Scenario, actor_user_id: int
) -> OrgState:
    org_state = OrgState(
        scenario_id=scenario.scenario_id,
        org_state_key="initial_state",
        name=DEFAULT_ORG_STATE_NAME,
        description=DEFAULT_ORG_STATE_DESCRIPTION,
        target_date=DEFAULT_ORG_STATE_TARGET_DATE,
        created_by=actor_user_id,
    )
    session.add(org_state)
    session.flush()
    return org_state


def link_initial_state(
    scenario: Scenario, org_state: OrgState, actor_user_id: int
) -> None:
    scenario.initial_state_id = org_state.org_state_id
    scenario.modified_by = actor_user_id


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
    actor_user_id: int,
) -> ScenarioResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = Scenario(
        organisation_id=organisation.organisation_id,
        scenario_key=_generate_scenario_key(),
        name=payload.name,
        description=payload.description,
        protected=False,
        created_by=actor_user_id,
    )
    session.add(scenario)
    session.commit()
    session.refresh(scenario)

    return to_scenario_response(scenario)


def copy_scenario(
    session: Session,
    organisation_key: str,
    payload: ScenarioCopyRequest,
    actor_user_id: int,
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
        created_by=actor_user_id,
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
        created_by=actor_user_id,
    )
    session.add(copied_org_state)
    session.flush()
    copied_scenario.initial_state_id = copied_org_state.org_state_id
    copied_scenario.modified_by = actor_user_id

    source_events = session.scalars(
        select(Event)
        .where(
            Event.scenario_id == source_scenario.scenario_id,
            Event.target_date <= source_org_state.target_date,
            Event.deleted_time.is_(None),
        )
        .order_by(Event.target_date, Event.event_id),
    ).all()
    for source_event in source_events:
        session.add(
            Event(
                scenario_id=copied_scenario.scenario_id,
                event_key=source_event.event_key,
                name=source_event.name,
                target_date=source_event.target_date,
                version=source_event.version,
                event_details=source_event.event_details,
                created_by=actor_user_id,
            ),
        )

    source_timeseries = session.scalars(
        select(Timeserie)
        .where(
            Timeserie.scenario_id == source_scenario.scenario_id,
            Timeserie.deleted_time.is_(None),
        )
        .order_by(Timeserie.timeserie_key, Timeserie.timeserie_id),
    ).all()
    copied_timeserie_id_by_source_id: dict[int, int] = {}
    for source_timeserie in source_timeseries:
        copied_timeserie = Timeserie(
            scenario_id=copied_scenario.scenario_id,
            timeserie_key=source_timeserie.timeserie_key,
            name=source_timeserie.name,
            short_name=source_timeserie.short_name,
            description=source_timeserie.description,
            unit=source_timeserie.unit,
            time_unit=source_timeserie.time_unit,
            value_unit=source_timeserie.value_unit,
            created_by=actor_user_id,
        )
        session.add(copied_timeserie)
        session.flush()
        copied_timeserie_id_by_source_id[source_timeserie.timeserie_id] = (
            copied_timeserie.timeserie_id
        )

        source_values = session.scalars(
            select(TimeserieValue)
            .where(
                TimeserieValue.timeserie_id == source_timeserie.timeserie_id,
                TimeserieValue.date <= source_org_state.target_date,
                TimeserieValue.deleted_time.is_(None),
            )
            .order_by(TimeserieValue.date, TimeserieValue.timeserie_value_id),
        ).all()
        for source_value in source_values:
            session.add(
                TimeserieValue(
                    timeserie_id=copied_timeserie.timeserie_id,
                    date=source_value.date,
                    value=deepcopy(source_value.value),
                    is_derived=source_value.is_derived,
                    created_by=actor_user_id,
                ),
            )

    source_equations = _active_derived_equations(session, source_scenario)
    for source_equation in source_equations:
        copied_derived_id = copied_timeserie_id_by_source_id.get(
            source_equation.derived_timeserie_id
        )
        copied_references = [
            copied_timeserie_id_by_source_id[source_id]
            for source_id in _equation_reference_ids(source_equation)
            if source_id in copied_timeserie_id_by_source_id
        ]
        if copied_derived_id is None or len(copied_references) != len(
            _equation_reference_ids(source_equation)
        ):
            continue
        session.add(
            DerivedMetricEquation(
                scenario_id=copied_scenario.scenario_id,
                derived_timeserie_id=copied_derived_id,
                formula=source_equation.formula,
                referenced_timeserie_ids=copied_references,
                created_by=actor_user_id,
            )
        )

    org_twin_structure_service.copy_graph_snapshots_for_org_states(
        session,
        {source_org_state.org_state_id: copied_org_state.org_state_id},
        copied_timeserie_id_by_source_id,
        actor_user_id,
    )

    session.commit()
    session.refresh(copied_scenario)

    return to_scenario_response(copied_scenario)


def patch_scenario(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    payload: ScenarioPatchRequest,
    actor_user_id: int,
) -> ScenarioResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)

    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data and payload.name is not None:
        scenario.name = payload.name
    if "description" in update_data:
        scenario.description = payload.description

    scenario.modified_time = datetime.now(UTC)
    scenario.modified_by = actor_user_id
    session.commit()
    session.refresh(scenario)

    return to_scenario_response(scenario)


def soft_delete_scenario(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    actor_user_id: int,
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

    _soft_delete_timeseries(session, scenario, now, actor_user_id)
    _soft_delete_events(session, scenario, now, actor_user_id)
    org_twin_structure_service.soft_delete_graph_structure_for_scenario(
        session,
        scenario.scenario_id,
        now,
        actor_user_id,
    )

    for org_state in active_org_states:
        org_state.deleted_time = now
        org_state.deleted_by = actor_user_id
        org_state.modified_time = now
        org_state.modified_by = actor_user_id

    scenario.deleted_time = now
    scenario.deleted_by = actor_user_id
    scenario.modified_time = now
    scenario.modified_by = actor_user_id
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
    actor_user_id: int,
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
            scenario.modified_by = actor_user_id

        org_twin_structure_service.soft_delete_graphs_for_org_states(
            session,
            cleaned_org_state_ids,
            now,
            actor_user_id,
        )

        for org_state in active_org_states:
            org_state.deleted_time = now
            org_state.deleted_by = actor_user_id
            org_state.modified_time = now
            org_state.modified_by = actor_user_id

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
    actor_user_id: int,
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
        created_by=actor_user_id,
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
    actor_user_id: int,
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
    org_state.modified_by = actor_user_id
    session.commit()
    session.refresh(org_state)

    return to_org_state_response(org_state)


def soft_delete_org_state(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    actor_user_id: int,
) -> None:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    org_state = _get_active_org_state(session, scenario, org_state_key)
    now = datetime.now(UTC)

    if scenario.initial_state_id == org_state.org_state_id:
        scenario.initial_state_id = None
        scenario.modified_time = now
        scenario.modified_by = actor_user_id

    org_twin_structure_service.soft_delete_graphs_for_org_states(
        session,
        [org_state.org_state_id],
        now,
        actor_user_id,
    )
    org_state.deleted_time = now
    org_state.deleted_by = actor_user_id
    org_state.modified_time = now
    org_state.modified_by = actor_user_id
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
    actor_user_id: int,
) -> EventResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)

    event = Event(
        scenario_id=scenario.scenario_id,
        event_key=_generate_event_key(),
        name=payload.name,
        target_date=payload.target_date,
        event_details=payload.event_details,
        created_by=actor_user_id,
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
    actor_user_id: int,
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
    event.modified_by = actor_user_id
    session.commit()
    session.refresh(event)

    return to_event_response(event)


def soft_delete_event(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    event_key: str,
    actor_user_id: int,
) -> None:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    event = _get_active_event(session, scenario, event_key)
    now = datetime.now(UTC)

    event.deleted_time = now
    event.deleted_by = actor_user_id
    event.modified_time = now
    event.modified_by = actor_user_id
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
    equation = _active_derived_equation_for_timeserie(session, timeserie)
    return to_timeserie_response(
        timeserie,
        values,
        equation=equation,
        short_name_editable=not _is_timeserie_referenced(session, scenario, timeserie),
    )


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

    equations = _active_derived_equations(session, scenario)
    equation_by_derived_id = {
        equation.derived_timeserie_id: equation for equation in equations
    }
    referenced_ids = {
        reference_id
        for equation in equations
        for reference_id in _equation_reference_ids(equation)
    }
    return [
        to_timeserie_response(
            timeserie,
            values_by_timeserie_id.get(timeserie.timeserie_id, []),
            equation=equation_by_derived_id.get(timeserie.timeserie_id),
            short_name_editable=timeserie.timeserie_id not in referenced_ids,
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

    timeserie = session.scalar(
        select(Timeserie).where(
            Timeserie.scenario_id == scenario.scenario_id,
            Timeserie.timeserie_key == normalised_key,
            Timeserie.deleted_time.is_(None),
        ),
    )

    return TimeserieExistsResponse(
        id=normalised_key,
        exists=timeserie is not None,
        shortName=(timeserie.short_name or "") if timeserie is not None else "",
        shortNameEditable=(
            not _is_timeserie_referenced(session, scenario, timeserie)
            if timeserie is not None
            else True
        ),
    )


def create_timeserie(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    payload: TimeserieCreateRequest,
    actor_user_id: int,
) -> TimeserieResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    _ensure_timeserie_key_available(session, scenario, payload.id)
    _ensure_timeserie_name_available(session, scenario, payload.name)
    _ensure_timeserie_short_name_available(session, scenario, payload.short_name)

    timeserie = Timeserie(
        scenario_id=scenario.scenario_id,
        timeserie_key=payload.id,
        name=payload.name,
        short_name=payload.short_name,
        description=payload.description,
        unit=payload.unit,
        time_unit=payload.time_unit,
        value_unit=payload.value_unit,
        created_by=actor_user_id,
    )
    session.add(timeserie)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "An active timeserie with this id, name, or short name already exists."
            ),
        ) from exc
    session.refresh(timeserie)

    return to_timeserie_response(timeserie)


def update_timeserie_short_name(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
    payload: TimeserieShortNamePatchRequest,
    actor_user_id: int,
) -> TimeserieResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    timeserie = _get_active_timeserie(session, scenario, timeserie_key, for_update=True)
    if _is_timeserie_referenced(session, scenario, timeserie):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A referenced timeserie short name cannot be changed.",
        )
    _ensure_timeserie_short_name_available(
        session,
        scenario,
        payload.short_name,
        excluding_timeserie_id=timeserie.timeserie_id,
    )
    timeserie.short_name = payload.short_name
    timeserie.modified_time = datetime.now(UTC)
    timeserie.modified_by = actor_user_id
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active timeserie with this short name already exists.",
        ) from exc
    session.refresh(timeserie)
    return to_timeserie_response(timeserie)


def create_derived_metric(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    payload: DerivedMetricCreateRequest,
    actor_user_id: int,
) -> TimeserieResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    _ensure_timeserie_name_available(session, scenario, payload.name)
    parsed, references, time_unit = _resolve_derived_formula(
        session, scenario, payload.formula
    )
    timeserie = Timeserie(
        scenario_id=scenario.scenario_id,
        timeserie_key=f"derived_{uuid4().hex}",
        name=payload.name,
        unit=payload.unit,
        time_unit=time_unit,
        value_unit="number",
        created_by=actor_user_id,
    )
    session.add(timeserie)
    session.flush()
    equation = DerivedMetricEquation(
        scenario_id=scenario.scenario_id,
        derived_timeserie_id=timeserie.timeserie_id,
        formula=parsed.source,
        referenced_timeserie_ids=[item.timeserie_id for item in references],
        created_by=actor_user_id,
    )
    session.add(equation)
    _materialize_derived_metric(
        session, equation, timeserie, parsed, references, actor_user_id
    )
    session.commit()
    session.refresh(timeserie)
    return to_timeserie_response(
        timeserie, _active_timeserie_values(session, timeserie), equation=equation
    )


def update_derived_metric(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
    payload: DerivedMetricPatchRequest,
    actor_user_id: int,
) -> TimeserieResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    timeserie = _get_active_timeserie(session, scenario, timeserie_key, for_update=True)
    equation = _active_derived_equation_for_timeserie(session, timeserie)
    if equation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Derived metric not found."
        )
    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data and payload.name is not None:
        _ensure_timeserie_name_available(
            session,
            scenario,
            payload.name,
            excluding_timeserie_id=timeserie.timeserie_id,
        )
        timeserie.name = payload.name
    if "unit" in update_data:
        timeserie.unit = payload.unit
    if "formula" in update_data and payload.formula is not None:
        parsed, references, time_unit = _resolve_derived_formula(
            session, scenario, payload.formula
        )
        equation.formula = parsed.source
        equation.referenced_timeserie_ids = [item.timeserie_id for item in references]
        equation.modified_time = datetime.now(UTC)
        equation.modified_by = actor_user_id
        timeserie.time_unit = time_unit
        _materialize_derived_metric(
            session, equation, timeserie, parsed, references, actor_user_id
        )
    timeserie.modified_time = datetime.now(UTC)
    timeserie.modified_by = actor_user_id
    session.commit()
    session.refresh(timeserie)
    return to_timeserie_response(
        timeserie, _active_timeserie_values(session, timeserie), equation=equation
    )


def replace_timeserie_values(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
    payload: TimeserieValuesPatchRequest,
    actor_user_id: int,
) -> TimeserieResponse:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    timeserie = _get_active_timeserie(
        session,
        scenario,
        _normalise_stable_key(timeserie_key, "Timeserie id must not be blank."),
        for_update=True,
    )
    if _active_derived_equation_for_timeserie(session, timeserie) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Derived timeserie values are calculated from its formula.",
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
            value.deleted_by = actor_user_id
            value.modified_time = now
            value.modified_by = actor_user_id

    for value_date, cell_value in replacement_values.items():
        stored_value: dict[str, object] = {"value": cell_value}
        existing_value = existing_by_date.get(value_date)
        if existing_value is None:
            session.add(
                TimeserieValue(
                    timeserie_id=timeserie.timeserie_id,
                    date=value_date,
                    value=stored_value,
                    created_by=actor_user_id,
                ),
            )
            continue

        existing_value.value = stored_value
        existing_value.deleted_time = None
        existing_value.deleted_by = None
        existing_value.modified_time = now
        existing_value.modified_by = actor_user_id

    timeserie.modified_time = now
    timeserie.modified_by = actor_user_id
    session.flush()
    _recalculate_dependent_derived_metrics(session, scenario, timeserie, actor_user_id)
    session.commit()
    session.refresh(timeserie)

    values = _active_timeserie_values(session, timeserie)
    return to_timeserie_response(
        timeserie,
        values,
        short_name_editable=not _is_timeserie_referenced(session, scenario, timeserie),
    )


def soft_delete_timeserie(
    session: Session,
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
    actor_user_id: int,
) -> None:
    organisation = _get_active_organisation(session, organisation_key)
    scenario = _get_active_scenario(session, organisation, scenario_key)
    timeserie = _get_active_timeserie(
        session,
        scenario,
        _normalise_stable_key(timeserie_key, "Timeserie id must not be blank."),
    )
    equation = _active_derived_equation_for_timeserie(session, timeserie)
    if equation is None and _is_timeserie_referenced(session, scenario, timeserie):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A timeserie referenced by a derived metric cannot be deleted.",
        )
    now = datetime.now(UTC)

    org_twin_structure_service.clear_timeserie_references(
        session,
        scenario.scenario_id,
        timeserie.timeserie_id,
        now,
        actor_user_id,
    )
    _soft_delete_timeserie_values(session, timeserie, now, actor_user_id)
    if equation is not None:
        equation.deleted_time = now
        equation.deleted_by = actor_user_id
        equation.modified_time = now
        equation.modified_by = actor_user_id
    timeserie.deleted_time = now
    timeserie.deleted_by = actor_user_id
    timeserie.modified_time = now
    timeserie.modified_by = actor_user_id
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
    *,
    equation: DerivedMetricEquation | None = None,
    short_name_editable: bool = True,
) -> TimeserieResponse:
    return TimeserieResponse(
        id=timeserie.timeserie_key,
        name=timeserie.name,
        shortName=timeserie.short_name or "",
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
        isDerived=equation is not None,
        derivedFormula=equation.formula if equation is not None else None,
        shortNameEditable=short_name_editable,
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


def _active_derived_equations(
    session: Session, scenario: Scenario
) -> list[DerivedMetricEquation]:
    return list(
        session.scalars(
            select(DerivedMetricEquation)
            .where(
                DerivedMetricEquation.scenario_id == scenario.scenario_id,
                DerivedMetricEquation.deleted_time.is_(None),
            )
            .order_by(DerivedMetricEquation.derived_metric_equation_id)
        ).all()
    )


def _active_derived_equation_for_timeserie(
    session: Session, timeserie: Timeserie
) -> DerivedMetricEquation | None:
    return session.scalar(
        select(DerivedMetricEquation).where(
            DerivedMetricEquation.derived_timeserie_id == timeserie.timeserie_id,
            DerivedMetricEquation.deleted_time.is_(None),
        )
    )


def _equation_reference_ids(equation: DerivedMetricEquation) -> list[int]:
    return list(equation.referenced_timeserie_ids)


def _is_timeserie_referenced(
    session: Session, scenario: Scenario, timeserie: Timeserie
) -> bool:
    return any(
        timeserie.timeserie_id in _equation_reference_ids(equation)
        for equation in _active_derived_equations(session, scenario)
    )


def _resolve_derived_formula(
    session: Session, scenario: Scenario, formula: str
) -> tuple[ParsedFormula, list[Timeserie], str]:
    try:
        parsed = parse_formula(formula)
    except FormulaError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error
    candidates = session.scalars(
        select(Timeserie).where(
            Timeserie.scenario_id == scenario.scenario_id,
            Timeserie.deleted_time.is_(None),
            Timeserie.short_name.in_(parsed.identifiers),
        )
    ).all()
    candidate_by_short_name = {
        item.short_name: item for item in candidates if item.short_name is not None
    }
    if len(candidate_by_short_name) != len(parsed.identifiers):
        missing = sorted(set(parsed.identifiers) - set(candidate_by_short_name))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown timeserie short name(s): {', '.join(missing)}.",
        )
    derived_ids = {
        equation.derived_timeserie_id
        for equation in _active_derived_equations(session, scenario)
    }
    references = [candidate_by_short_name[name] for name in parsed.identifiers]
    if any(item.timeserie_id in derived_ids for item in references):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Derived metrics cannot be referenced by another derived formula.",
        )
    if any(item.value_unit != "number" for item in references):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Derived formulas can reference only numeric timeseries.",
        )
    time_units = {item.time_unit for item in references}
    if len(time_units) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Derived formula references must have the same time unit.",
        )
    return parsed, references, time_units.pop()


def _materialize_derived_metric(
    session: Session,
    equation: DerivedMetricEquation,
    derived: Timeserie,
    parsed: ParsedFormula,
    references: list[Timeserie],
    actor_user_id: int,
) -> None:
    session.flush()
    values_by_reference: dict[str, dict[dt_date, float]] = {}
    for reference in references:
        if reference.short_name is None:
            continue
        values: dict[dt_date, float] = {}
        for item in _active_timeserie_values(session, reference):
            value = item.value.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if math.isfinite(float(value)):
                    values[item.date] = float(value)
        values_by_reference[reference.short_name] = values
    date_sets: list[set[dt_date]] = [
        set(values) for values in values_by_reference.values()
    ]
    dates: set[dt_date] = set(date_sets[0])
    for date_set in date_sets[1:]:
        dates.intersection_update(date_set)
    replacement: dict[dt_date, float] = {}
    for value_date in dates:
        try:
            replacement[value_date] = evaluate_formula(
                parsed,
                {
                    name: values[value_date]
                    for name, values in values_by_reference.items()
                },
            )
        except FormulaError:
            continue
    now = datetime.now(UTC)
    existing = session.scalars(
        select(TimeserieValue).where(
            TimeserieValue.timeserie_id == derived.timeserie_id
        )
    ).all()
    existing_by_date = {item.date: item for item in existing}
    for item in existing:
        if item.deleted_time is None and item.date not in replacement:
            item.deleted_time = now
            item.deleted_by = actor_user_id
            item.modified_time = now
            item.modified_by = actor_user_id
    for value_date, value in replacement.items():
        item = existing_by_date.get(value_date)
        if item is None:
            session.add(
                TimeserieValue(
                    timeserie_id=derived.timeserie_id,
                    date=value_date,
                    value={"value": value},
                    is_derived=True,
                    created_by=actor_user_id,
                )
            )
            continue
        item.value = {"value": value}
        item.is_derived = True
        item.deleted_time = None
        item.deleted_by = None
        item.modified_time = now
        item.modified_by = actor_user_id


def _recalculate_dependent_derived_metrics(
    session: Session, scenario: Scenario, source: Timeserie, actor_user_id: int
) -> None:
    for equation in _active_derived_equations(session, scenario):
        if source.timeserie_id not in _equation_reference_ids(equation):
            continue
        derived = session.get(Timeserie, equation.derived_timeserie_id)
        if derived is None or derived.deleted_time is not None:
            continue
        references = list(
            session.scalars(
                select(Timeserie).where(
                    Timeserie.timeserie_id.in_(_equation_reference_ids(equation))
                )
            ).all()
        )
        try:
            parsed = parse_formula(equation.formula)
        except FormulaError:
            continue
        _materialize_derived_metric(
            session, equation, derived, parsed, references, actor_user_id
        )


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
    actor_user_id: int,
) -> None:
    events = session.scalars(
        select(Event).where(
            Event.scenario_id == scenario.scenario_id,
            Event.deleted_time.is_(None),
        ),
    ).all()

    for event in events:
        event.deleted_time = deleted_time
        event.deleted_by = actor_user_id
        event.modified_time = deleted_time
        event.modified_by = actor_user_id


def _soft_delete_timeseries(
    session: Session,
    scenario: Scenario,
    deleted_time: datetime,
    actor_user_id: int,
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
            value.deleted_by = actor_user_id
            value.modified_time = deleted_time
            value.modified_by = actor_user_id

    for timeserie in timeseries:
        timeserie.deleted_time = deleted_time
        timeserie.deleted_by = actor_user_id
        timeserie.modified_time = deleted_time
        timeserie.modified_by = actor_user_id

    for equation in _active_derived_equations(session, scenario):
        equation.deleted_time = deleted_time
        equation.deleted_by = actor_user_id
        equation.modified_time = deleted_time
        equation.modified_by = actor_user_id


def _soft_delete_timeserie_values(
    session: Session,
    timeserie: Timeserie,
    deleted_time: datetime,
    actor_user_id: int,
) -> None:
    values = session.scalars(
        select(TimeserieValue).where(
            TimeserieValue.timeserie_id == timeserie.timeserie_id,
            TimeserieValue.deleted_time.is_(None),
        ),
    ).all()

    for value in values:
        value.deleted_time = deleted_time
        value.deleted_by = actor_user_id
        value.modified_time = deleted_time
        value.modified_by = actor_user_id


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


def _ensure_timeserie_name_available(
    session: Session,
    scenario: Scenario,
    name: str,
    excluding_timeserie_id: int | None = None,
) -> None:
    query = select(Timeserie.timeserie_id).where(
        Timeserie.scenario_id == scenario.scenario_id,
        func.lower(func.trim(Timeserie.name)) == name.lower(),
        Timeserie.deleted_time.is_(None),
    )
    if excluding_timeserie_id is not None:
        query = query.where(Timeserie.timeserie_id != excluding_timeserie_id)
    timeserie_id = session.scalar(query)
    if timeserie_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active timeserie with this name already exists.",
        )


def _ensure_timeserie_short_name_available(
    session: Session,
    scenario: Scenario,
    short_name: str | None,
    excluding_timeserie_id: int | None = None,
) -> None:
    if short_name is None:
        return

    query = select(Timeserie.timeserie_id).where(
        Timeserie.scenario_id == scenario.scenario_id,
        Timeserie.short_name == short_name,
        Timeserie.deleted_time.is_(None),
    )
    if excluding_timeserie_id is not None:
        query = query.where(Timeserie.timeserie_id != excluding_timeserie_id)
    timeserie_id = session.scalar(query)
    if timeserie_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active timeserie with this short name already exists.",
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
