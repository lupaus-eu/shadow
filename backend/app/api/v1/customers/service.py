from collections.abc import Callable
from datetime import UTC, datetime
from typing import Never, cast

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.customers.models import Contact, Customer, CustomerAddress
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


def _not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found.",
    )


def _commit(session: Session) -> None:
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def _mutate_and_commit(session: Session, mutation: Callable[[], None]) -> None:
    try:
        mutation()
        session.commit()
    except Exception:
        session.rollback()
        raise


def _raise_not_found(resource: str) -> Never:
    raise _not_found(resource)


def _get_customer_record(session: Session, customer_id: int) -> Customer:
    customer = session.scalar(
        select(Customer).where(
            Customer.customer_id == customer_id,
            Customer.deleted_time.is_(None),
            Customer.status.in_(("active", "archived")),
        ),
    )
    return customer if customer is not None else _raise_not_found("Customer")


def _get_contact_record(
    session: Session,
    customer_id: int,
    contact_id: int,
) -> Contact:
    contact = session.scalar(
        select(Contact).where(
            Contact.contact_id == contact_id,
            Contact.customer_id == customer_id,
            Contact.deleted_time.is_(None),
        ),
    )
    return contact if contact is not None else _raise_not_found("Contact")


def _get_address_record(
    session: Session,
    customer_id: int,
    address_id: int,
) -> CustomerAddress:
    address = session.scalar(
        select(CustomerAddress).where(
            CustomerAddress.customer_address_id == address_id,
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.deleted_time.is_(None),
        ),
    )
    return address if address is not None else _raise_not_found("Address")


def _customer_response(customer: Customer) -> CustomerResponse:
    return CustomerResponse(
        id=customer.customer_id,
        name=customer.name,
        email=customer.email,
        status=cast(CustomerStatus, customer.status),
        created_at=customer.created_time,
        updated_at=customer.modified_time,
    )


def _contact_response(contact: Contact) -> ContactResponse:
    return ContactResponse(
        id=contact.contact_id,
        name=contact.name,
        email=contact.email,
        phone=contact.phone,
        job_title=contact.job_title,
        created_at=contact.created_time,
        updated_at=contact.modified_time,
    )


def _address_response(address: CustomerAddress) -> AddressResponse:
    return AddressResponse(
        id=address.customer_address_id,
        label=address.label,
        address_line_1=address.address_line_1,
        address_line_2=address.address_line_2,
        postal_code=address.postal_code,
        city=address.city,
        region=address.region,
        country_code=address.country_code,
        created_at=address.created_time,
        updated_at=address.modified_time,
    )


def list_customers(
    session: Session,
    q: str | None = None,
    customer_status: CustomerStatus | None = None,
) -> list[CustomerResponse]:
    query = select(Customer).where(
        Customer.deleted_time.is_(None),
        Customer.status.in_(("active", "archived")),
    )
    normalized_q = q.strip().lower() if q is not None else ""
    if normalized_q:
        query = query.where(
            or_(
                func.lower(Customer.name).contains(normalized_q, autoescape=True),
                func.lower(Customer.email).contains(normalized_q, autoescape=True),
            ),
        )
    if customer_status is not None:
        query = query.where(Customer.status == customer_status)
    customers = session.scalars(
        query.order_by(func.lower(Customer.name), Customer.customer_id),
    ).all()
    return [_customer_response(customer) for customer in customers]


def get_customer(session: Session, customer_id: int) -> CustomerResponse:
    return _customer_response(_get_customer_record(session, customer_id))


def create_customer(
    session: Session,
    payload: CustomerCreateRequest,
) -> CustomerResponse:
    customer = Customer(name=payload.name, email=payload.email, status="active")
    session.add(customer)
    _commit(session)
    session.refresh(customer)
    return _customer_response(customer)


def replace_customer(
    session: Session,
    customer_id: int,
    payload: CustomerReplaceRequest,
) -> CustomerResponse:
    customer = _get_customer_record(session, customer_id)
    customer.name = payload.name
    customer.email = payload.email
    customer.status = payload.status
    customer.modified_time = datetime.now(UTC)
    _commit(session)
    session.refresh(customer)
    return _customer_response(customer)


def delete_customer(session: Session, customer_id: int) -> None:
    customer = _get_customer_record(session, customer_id)
    contacts = session.scalars(
        select(Contact).where(
            Contact.customer_id == customer_id,
            Contact.deleted_time.is_(None),
        ),
    ).all()
    addresses = session.scalars(
        select(CustomerAddress).where(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.deleted_time.is_(None),
        ),
    ).all()
    now = datetime.now(UTC)

    def mutation() -> None:
        for contact in contacts:
            contact.deleted_time = now
            contact.modified_time = now
        for address in addresses:
            address.deleted_time = now
            address.modified_time = now
        customer.status = "deleted"
        customer.deleted_time = now
        customer.modified_time = now

    _mutate_and_commit(session, mutation)


def list_contacts(session: Session, customer_id: int) -> list[ContactResponse]:
    _get_customer_record(session, customer_id)
    contacts = session.scalars(
        select(Contact)
        .where(
            Contact.customer_id == customer_id,
            Contact.deleted_time.is_(None),
        )
        .order_by(func.lower(Contact.name), Contact.contact_id),
    ).all()
    return [_contact_response(contact) for contact in contacts]


def create_contact(
    session: Session,
    customer_id: int,
    payload: ContactWriteRequest,
) -> ContactResponse:
    _get_customer_record(session, customer_id)
    contact = Contact(customer_id=customer_id, **payload.model_dump(by_alias=False))
    session.add(contact)
    _commit(session)
    session.refresh(contact)
    return _contact_response(contact)


def replace_contact(
    session: Session,
    customer_id: int,
    contact_id: int,
    payload: ContactWriteRequest,
) -> ContactResponse:
    _get_customer_record(session, customer_id)
    contact = _get_contact_record(session, customer_id, contact_id)
    for key, value in payload.model_dump(by_alias=False).items():
        setattr(contact, key, value)
    contact.modified_time = datetime.now(UTC)
    _commit(session)
    session.refresh(contact)
    return _contact_response(contact)


def delete_contact(session: Session, customer_id: int, contact_id: int) -> None:
    _get_customer_record(session, customer_id)
    contact = _get_contact_record(session, customer_id, contact_id)
    now = datetime.now(UTC)
    contact.deleted_time = now
    contact.modified_time = now
    _commit(session)


def list_addresses(session: Session, customer_id: int) -> list[AddressResponse]:
    _get_customer_record(session, customer_id)
    addresses = session.scalars(
        select(CustomerAddress)
        .where(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.deleted_time.is_(None),
        )
        .order_by(
            func.lower(CustomerAddress.label),
            CustomerAddress.customer_address_id,
        ),
    ).all()
    return [_address_response(address) for address in addresses]


def create_address(
    session: Session,
    customer_id: int,
    payload: AddressWriteRequest,
) -> AddressResponse:
    _get_customer_record(session, customer_id)
    address = CustomerAddress(
        customer_id=customer_id,
        **payload.model_dump(by_alias=False),
    )
    session.add(address)
    _commit(session)
    session.refresh(address)
    return _address_response(address)


def replace_address(
    session: Session,
    customer_id: int,
    address_id: int,
    payload: AddressWriteRequest,
) -> AddressResponse:
    _get_customer_record(session, customer_id)
    address = _get_address_record(session, customer_id, address_id)
    for key, value in payload.model_dump(by_alias=False).items():
        setattr(address, key, value)
    address.modified_time = datetime.now(UTC)
    _commit(session)
    session.refresh(address)
    return _address_response(address)


def delete_address(session: Session, customer_id: int, address_id: int) -> None:
    _get_customer_record(session, customer_id)
    address = _get_address_record(session, customer_id, address_id)
    now = datetime.now(UTC)
    address.deleted_time = now
    address.modified_time = now
    _commit(session)
