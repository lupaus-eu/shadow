from typing import Annotated

from fastapi import APIRouter, Depends, status
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
    response_model=PredictionVersionDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_prediction(
    organisation_key: str,
    payload: PredictionCreateRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> PredictionVersionDetailResponse:
    return service.create_prediction(
        session, organisation_key, payload, active.user.user_id
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
