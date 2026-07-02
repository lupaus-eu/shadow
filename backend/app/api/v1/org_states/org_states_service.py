import logging
from datetime import UTC, datetime
from datetime import date as dt_date
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
    OrgStateCreateRequest,
    OrgStatePatchRequest,
    OrgStateResponse,
    ScenarioCopyRequest,
    ScenarioCreateRequest,
    ScenarioPatchRequest,
    ScenarioResponse,
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
    source_boundary_org_state = _get_active_org_state(
        session,
        source_scenario,
        payload.source_org_state_id,
    )

    copied_scenario = Scenario(
        organisation_id=organisation.organisation_id,
        scenario_key=_generate_scenario_key(),
        name=payload.name,
        description=payload.description,
        protected=False,
        source_scenario_id=source_scenario.scenario_id,
    )
    session.add(copied_scenario)
    session.flush()

    source_org_states = session.scalars(
        select(OrgState)
        .where(
            OrgState.scenario_id == source_scenario.scenario_id,
            OrgState.deleted_time.is_(None),
            OrgState.target_date <= source_boundary_org_state.target_date,
        )
        .order_by(OrgState.target_date, OrgState.org_state_id),
    ).all()

    copied_org_state_id_by_source_id: dict[int, int] = {}
    for source_org_state in source_org_states:
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
        copied_org_state_id_by_source_id[source_org_state.org_state_id] = (
            copied_org_state.org_state_id
        )

    copied_initial_state_id = copied_org_state_id_by_source_id.get(
        source_boundary_org_state.org_state_id,
    )
    if copied_initial_state_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Copied source organisation state was not created.",
        )
    copied_scenario.initial_state_id = copied_initial_state_id

    org_twin_structure_service.copy_graph_snapshots_for_org_states(
        session,
        copied_org_state_id_by_source_id,
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
    org_state_ids = [org_state.org_state_id for org_state in active_org_states]

    _soft_delete_timeseries(session, scenario, now)
    _soft_delete_events(session, scenario, now)
    org_twin_structure_service.soft_delete_graphs_for_org_states(
        session,
        org_state_ids,
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


def _ensure_scenario_allows_destructive_action(scenario: Scenario) -> None:
    if scenario.protected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Protected scenarios cannot be deleted or cleaned.",
        )


def _generate_scenario_key() -> str:
    return f"scenario_{uuid4().hex}"


def _generate_org_state_key() -> str:
    return f"org_state_{uuid4().hex}"
