from datetime import date as dt_date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.org_states.models import OrgState, Scenario
from app.api.v1.org_states.schemas import OrgStateResponse, ScenarioResponse
from app.api.v1.organisations.models import Organisation

DEFAULT_SCENARIO_NAME = "Reality"
DEFAULT_SCENARIO_DESCRIPTION = "The reality of the organisation"
DEFAULT_SCENARIO_PROTECTED = True
DEFAULT_ORG_STATE_NAME = "Initial state"
DEFAULT_ORG_STATE_DESCRIPTION = "Initial state of reality"
DEFAULT_ORG_STATE_TARGET_DATE = dt_date(2020, 1, 1)


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


def _get_active_scenario(
    session: Session,
    organisation: Organisation,
    scenario_key: str,
) -> Scenario:
    scenario = session.scalar(
        select(Scenario).where(
            Scenario.organisation_id == organisation.organisation_id,
            Scenario.scenario_key == scenario_key,
            Scenario.deleted_time.is_(None),
        ),
    )

    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scenario not found.",
        )

    return scenario
