from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    UnsafeRequestDependency,
    require_business_request,
)
from app.api.v1.org_states import org_states_service
from app.api.v1.org_states.schemas import (
    EventCreateRequest,
    EventPatchRequest,
    EventResponse,
    OrgStateCreateRequest,
    OrgStatePatchRequest,
    OrgStateResponse,
    OrgStatesCleanResponse,
    ScenarioCopyRequest,
    ScenarioCreateRequest,
    ScenarioPatchRequest,
    ScenarioResponse,
    TimeserieCreateRequest,
    TimeserieExistsResponse,
    TimeserieResponse,
    TimeserieValuesPatchRequest,
)
from app.core.database import get_db_session

router = APIRouter(
    prefix="/organisations",
    tags=["org-states"],
    dependencies=[Depends(require_business_request)],
)
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("/{organisation_key}/scenarios", response_model=list[ScenarioResponse])
def list_organisation_scenarios(
    organisation_key: str,
    session: SessionDependency,
) -> list[ScenarioResponse]:
    return org_states_service.list_organisation_scenarios(session, organisation_key)


@router.post(
    "/{organisation_key}/scenarios",
    response_model=ScenarioResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_scenario(
    organisation_key: str,
    payload: ScenarioCreateRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> ScenarioResponse:
    return org_states_service.create_scenario(
        session, organisation_key, payload, active.user.user_id
    )


@router.post(
    "/{organisation_key}/scenarios/copy",
    response_model=ScenarioResponse,
    status_code=status.HTTP_201_CREATED,
)
def copy_scenario(
    organisation_key: str,
    payload: ScenarioCopyRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> ScenarioResponse:
    return org_states_service.copy_scenario(
        session, organisation_key, payload, active.user.user_id
    )


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}",
    response_model=ScenarioResponse,
)
def get_scenario(
    organisation_key: str,
    scenario_key: str,
    session: SessionDependency,
) -> ScenarioResponse:
    return org_states_service.get_scenario(session, organisation_key, scenario_key)


@router.patch(
    "/{organisation_key}/scenarios/{scenario_key}",
    response_model=ScenarioResponse,
)
def patch_scenario(
    organisation_key: str,
    scenario_key: str,
    payload: ScenarioPatchRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> ScenarioResponse:
    return org_states_service.patch_scenario(
        session,
        organisation_key,
        scenario_key,
        payload,
        active.user.user_id,
    )


@router.delete(
    "/{organisation_key}/scenarios/{scenario_key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_scenario(
    organisation_key: str,
    scenario_key: str,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> Response:
    org_states_service.soft_delete_scenario(
        session, organisation_key, scenario_key, active.user.user_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{organisation_key}/scenarios/{scenario_key}/timeseries",
    response_model=TimeserieResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_timeserie(
    organisation_key: str,
    scenario_key: str,
    payload: TimeserieCreateRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> TimeserieResponse:
    return org_states_service.create_timeserie(
        session,
        organisation_key,
        scenario_key,
        payload,
        active.user.user_id,
    )


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}/timeseries",
    response_model=list[TimeserieResponse],
)
def list_scenario_timeseries(
    organisation_key: str,
    scenario_key: str,
    session: SessionDependency,
) -> list[TimeserieResponse]:
    return org_states_service.list_scenario_timeseries(
        session,
        organisation_key,
        scenario_key,
    )


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}",
    response_model=TimeserieResponse,
)
def get_timeserie(
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
    session: SessionDependency,
) -> TimeserieResponse:
    return org_states_service.get_timeserie(
        session,
        organisation_key,
        scenario_key,
        timeserie_key,
    )


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}/exists",
    response_model=TimeserieExistsResponse,
)
def timeserie_exists(
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
    session: SessionDependency,
) -> TimeserieExistsResponse:
    return org_states_service.timeserie_exists(
        session,
        organisation_key,
        scenario_key,
        timeserie_key,
    )


@router.patch(
    "/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}/values",
    response_model=TimeserieResponse,
)
def replace_timeserie_values(
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
    payload: TimeserieValuesPatchRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> TimeserieResponse:
    return org_states_service.replace_timeserie_values(
        session,
        organisation_key,
        scenario_key,
        timeserie_key,
        payload,
        active.user.user_id,
    )


@router.delete(
    "/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_timeserie(
    organisation_key: str,
    scenario_key: str,
    timeserie_key: str,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> Response:
    org_states_service.soft_delete_timeserie(
        session,
        organisation_key,
        scenario_key,
        timeserie_key,
        active.user.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}/org-states",
    response_model=list[OrgStateResponse],
)
def list_organisation_scenario_org_states(
    organisation_key: str,
    scenario_key: str,
    session: SessionDependency,
) -> list[OrgStateResponse]:
    return org_states_service.list_organisation_scenario_org_states(
        session,
        organisation_key,
        scenario_key,
    )


@router.post(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/clean",
    response_model=OrgStatesCleanResponse,
)
def clean_org_states(
    organisation_key: str,
    scenario_key: str,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> OrgStatesCleanResponse:
    cleaned = org_states_service.clean_org_states(
        session,
        organisation_key,
        scenario_key,
        active.user.user_id,
    )
    return OrgStatesCleanResponse(cleaned=cleaned)


@router.post(
    "/{organisation_key}/scenarios/{scenario_key}/org-states",
    response_model=OrgStateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_org_state(
    organisation_key: str,
    scenario_key: str,
    payload: OrgStateCreateRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> OrgStateResponse:
    return org_states_service.create_org_state(
        session,
        organisation_key,
        scenario_key,
        payload,
        active.user.user_id,
    )


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}",
    response_model=OrgStateResponse,
)
def get_org_state(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    session: SessionDependency,
) -> OrgStateResponse:
    return org_states_service.get_org_state(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
    )


@router.patch(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}",
    response_model=OrgStateResponse,
)
def patch_org_state(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    payload: OrgStatePatchRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> OrgStateResponse:
    return org_states_service.patch_org_state(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
        payload,
        active.user.user_id,
    )


@router.delete(
    "/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_org_state(
    organisation_key: str,
    scenario_key: str,
    org_state_key: str,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> Response:
    org_states_service.soft_delete_org_state(
        session,
        organisation_key,
        scenario_key,
        org_state_key,
        active.user.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}/events",
    response_model=list[EventResponse],
)
def list_scenario_events(
    organisation_key: str,
    scenario_key: str,
    session: SessionDependency,
) -> list[EventResponse]:
    return org_states_service.list_scenario_events(
        session,
        organisation_key,
        scenario_key,
    )


@router.post(
    "/{organisation_key}/scenarios/{scenario_key}/events",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    organisation_key: str,
    scenario_key: str,
    payload: EventCreateRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> EventResponse:
    return org_states_service.create_event(
        session,
        organisation_key,
        scenario_key,
        payload,
        active.user.user_id,
    )


@router.get(
    "/{organisation_key}/scenarios/{scenario_key}/events/{event_id}",
    response_model=EventResponse,
)
def get_event(
    organisation_key: str,
    scenario_key: str,
    event_id: str,
    session: SessionDependency,
) -> EventResponse:
    return org_states_service.get_event(
        session,
        organisation_key,
        scenario_key,
        event_id,
    )


@router.patch(
    "/{organisation_key}/scenarios/{scenario_key}/events/{event_id}",
    response_model=EventResponse,
)
def patch_event(
    organisation_key: str,
    scenario_key: str,
    event_id: str,
    payload: EventPatchRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> EventResponse:
    return org_states_service.patch_event(
        session,
        organisation_key,
        scenario_key,
        event_id,
        payload,
        active.user.user_id,
    )


@router.delete(
    "/{organisation_key}/scenarios/{scenario_key}/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_event(
    organisation_key: str,
    scenario_key: str,
    event_id: str,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> Response:
    org_states_service.soft_delete_event(
        session,
        organisation_key,
        scenario_key,
        event_id,
        active.user.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
