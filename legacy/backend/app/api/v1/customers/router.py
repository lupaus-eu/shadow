from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    UnsafeRequestDependency,
    require_business_request,
)
from app.api.v1.customers import service
from app.api.v1.customers.schemas import (
    AddressResponse,
    AddressWriteRequest,
    ContactResponse,
    ContactWriteRequest,
    CustomerCreateRequest,
    CustomerReplaceRequest,
    CustomerResponse,
    CustomerStatus,
)
from app.core.database import get_db_session

router = APIRouter(
    prefix="/customers",
    tags=["customers"],
    dependencies=[Depends(require_business_request)],
)
SessionDependency = Annotated[Session, Depends(get_db_session)]


@router.get("", response_model=list[CustomerResponse])
def list_customers(
    session: SessionDependency,
    q: Annotated[str | None, Query()] = None,
    customer_status: Annotated[CustomerStatus | None, Query(alias="status")] = None,
) -> list[CustomerResponse]:
    return service.list_customers(session, q, customer_status)


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, session: SessionDependency) -> CustomerResponse:
    return service.get_customer(session, customer_id)


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreateRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> CustomerResponse:
    return service.create_customer(session, payload, active.user.user_id)


@router.put("/{customer_id}", response_model=CustomerResponse)
def replace_customer(
    customer_id: int,
    payload: CustomerReplaceRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> CustomerResponse:
    return service.replace_customer(session, customer_id, payload, active.user.user_id)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: int,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> Response:
    service.delete_customer(session, customer_id, active.user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{customer_id}/contacts", response_model=list[ContactResponse])
def list_contacts(
    customer_id: int,
    session: SessionDependency,
) -> list[ContactResponse]:
    return service.list_contacts(session, customer_id)


@router.post(
    "/{customer_id}/contacts",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_contact(
    customer_id: int,
    payload: ContactWriteRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> ContactResponse:
    return service.create_contact(session, customer_id, payload, active.user.user_id)


@router.put(
    "/{customer_id}/contacts/{contact_id}",
    response_model=ContactResponse,
)
def replace_contact(
    customer_id: int,
    contact_id: int,
    payload: ContactWriteRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> ContactResponse:
    return service.replace_contact(
        session, customer_id, contact_id, payload, active.user.user_id
    )


@router.delete(
    "/{customer_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_contact(
    customer_id: int,
    contact_id: int,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> Response:
    service.delete_contact(session, customer_id, contact_id, active.user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{customer_id}/addresses", response_model=list[AddressResponse])
def list_addresses(
    customer_id: int,
    session: SessionDependency,
) -> list[AddressResponse]:
    return service.list_addresses(session, customer_id)


@router.post(
    "/{customer_id}/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_address(
    customer_id: int,
    payload: AddressWriteRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> AddressResponse:
    return service.create_address(session, customer_id, payload, active.user.user_id)


@router.put(
    "/{customer_id}/addresses/{address_id}",
    response_model=AddressResponse,
)
def replace_address(
    customer_id: int,
    address_id: int,
    payload: AddressWriteRequest,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> AddressResponse:
    return service.replace_address(
        session, customer_id, address_id, payload, active.user.user_id
    )


@router.delete(
    "/{customer_id}/addresses/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_address(
    customer_id: int,
    address_id: int,
    session: SessionDependency,
    active: UnsafeRequestDependency,
) -> Response:
    service.delete_address(session, customer_id, address_id, active.user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
