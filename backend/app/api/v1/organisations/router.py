from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.v1.organisations import service
from app.api.v1.organisations.schemas import (
    OrganisationCreateRequest,
    OrganisationPatchRequest,
    OrganisationResponse,
)
from app.core.database import get_db_session

router = APIRouter(prefix="/organisations", tags=["organisations"])
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=list[OrganisationResponse])
def list_organisations(
    session: SessionDependency,
) -> list[OrganisationResponse]:
    return service.list_organisations(session)


@router.get("/{organisation_key}", response_model=OrganisationResponse)
def get_organisation(
    organisation_key: str,
    session: SessionDependency,
) -> OrganisationResponse:
    return service.get_organisation(session, organisation_key)


@router.post(
    "",
    response_model=OrganisationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organisation(
    payload: OrganisationCreateRequest,
    session: SessionDependency,
) -> OrganisationResponse:
    return service.create_organisation(session, payload)


@router.patch("/{organisation_key}", response_model=OrganisationResponse)
def patch_organisation(
    organisation_key: str,
    payload: OrganisationPatchRequest,
    session: SessionDependency,
) -> OrganisationResponse:
    return service.patch_organisation(session, organisation_key, payload)


@router.delete("/{organisation_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organisation(
    organisation_key: str,
    session: SessionDependency,
) -> Response:
    service.soft_delete_organisation(session, organisation_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
