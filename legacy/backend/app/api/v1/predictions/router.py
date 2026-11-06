from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    UnsafeRequestDependency,
    require_business_request,
)
from app.api.v1.predictions import service
from app.api.v1.predictions.schemas import (
    PredictionCreateRequest,
    PredictionPreflightRequest,
    PredictionPreflightResponse,
    PredictionRequestSummaryResponse,
    PredictionVersionDetailResponse,
    PredictionVersionListResponse,
)
from app.core.database import get_db_session

router = APIRouter(
    prefix="/organisations",
    tags=["predictions"],
    dependencies=[Depends(require_business_request)],
)
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.post(
    "/{organisation_key}/predictions/preflight",
    response_model=PredictionPreflightResponse,
)
def preflight_predictions(
    organisation_key: str,
    payload: PredictionPreflightRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> PredictionPreflightResponse:
    return service.preflight_predictions(session, organisation_key, payload)


@router.post(
    "/{organisation_key}/predictions",
    response_model=PredictionRequestSummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_prediction(
    organisation_key: str,
    payload: PredictionCreateRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> Response:
    request = service.enqueue_prediction(
        session, organisation_key, payload, active.user.user_id
    )
    location = (
        f"/api/v1/organisations/{organisation_key}/prediction-requests/{request.id}"
    )
    return Response(
        content=request.model_dump_json(by_alias=True),
        status_code=status.HTTP_202_ACCEPTED,
        media_type="application/json",
        headers={"Location": location},
    )


@router.get(
    "/{organisation_key}/prediction-requests",
    response_model=list[PredictionRequestSummaryResponse],
)
def list_prediction_requests(
    organisation_key: str, session: SessionDependency
) -> list[PredictionRequestSummaryResponse]:
    return service.list_prediction_requests(session, organisation_key)


@router.get(
    "/{organisation_key}/prediction-requests/{request_key}",
    response_model=PredictionRequestSummaryResponse,
)
def get_prediction_request(
    organisation_key: str, request_key: str, session: SessionDependency
) -> PredictionRequestSummaryResponse:
    return service.get_prediction_request(session, organisation_key, request_key)


@router.post(
    "/{organisation_key}/prediction-requests/{request_key}/cancel",
    response_model=PredictionRequestSummaryResponse,
)
def cancel_prediction_request(
    organisation_key: str,
    request_key: str,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> PredictionRequestSummaryResponse:
    return service.cancel_prediction_request(
        session, organisation_key, request_key, active.user.user_id
    )


@router.get(
    "/{organisation_key}/predictions",
    response_model=list[PredictionVersionListResponse],
)
def list_predictions(
    organisation_key: str, session: SessionDependency
) -> list[PredictionVersionListResponse]:
    return service.list_predictions(session, organisation_key)


@router.get(
    "/{organisation_key}/predictions/{prediction_key}",
    response_model=PredictionVersionDetailResponse,
)
def get_prediction(
    organisation_key: str, prediction_key: str, session: SessionDependency
) -> PredictionVersionDetailResponse:
    return service.get_prediction(session, organisation_key, prediction_key)
