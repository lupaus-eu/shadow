from collections.abc import Iterator
from typing import Any

import pytest
from auth_helpers import authenticate_test_client
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import StaticPool, create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.customers import service
from app.api.v1.customers.models import Contact, Customer, CustomerAddress
from app.api.v1.customers.schemas import (
    AddressWriteRequest,
    ContactWriteRequest,
    CustomerCreateRequest,
)
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autocommit=False, autoflush=False)
    engine.dispose()


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()

    def override_get_db_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as test_client:
        authenticate_test_client(test_client, session_factory)
        yield test_client
    app.dependency_overrides.clear()


def _create_customer(
    client: TestClient,
    name: str = "Acme",
    email: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/customers",
        json={"name": name, "email": email},
    )
    assert response.status_code == 201
    return response.json()


def test_customer_schemas_normalize_and_validate_values() -> None:
    customer = CustomerCreateRequest(name="  Acme  ", email="  info@acme.test  ")
    contact = ContactWriteRequest(
        name="  Ada  ",
        email=" ",
        phone="  +358 1  ",
        jobTitle="   ",
    )
    address = AddressWriteRequest(
        label="  Billing  ",
        addressLine1="  Main street 1  ",
        addressLine2=" ",
        postalCode=" 00100 ",
        city=" Helsinki ",
        region=" ",
        countryCode=" fi ",
    )

    assert customer.name == "Acme"
    assert customer.email == "info@acme.test"
    assert contact.model_dump(by_alias=True) == {
        "name": "Ada",
        "email": None,
        "phone": "+358 1",
        "jobTitle": None,
    }
    assert address.model_dump(by_alias=True) == {
        "label": "Billing",
        "addressLine1": "Main street 1",
        "addressLine2": None,
        "postalCode": "00100",
        "city": "Helsinki",
        "region": None,
        "countryCode": "FI",
    }

    with pytest.raises(ValidationError):
        CustomerCreateRequest(name=" \t ", email=None)
    with pytest.raises(ValidationError):
        CustomerCreateRequest(name="Acme", email="not-an-email")
    with pytest.raises(ValidationError):
        AddressWriteRequest(
            label="Billing",
            addressLine1="Street",
            countryCode="F1",
        )
    with pytest.raises(ValidationError):
        ContactWriteRequest(name="Ada", unexpected=True)  # type: ignore[call-arg]

    for payload in (
        {"name": 123},
        {"name": "Acme", "email": 123},
    ):
        with pytest.raises(ValidationError):
            CustomerCreateRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        ContactWriteRequest.model_validate({"name": "Ada", "phone": 123})
    with pytest.raises(ValidationError):
        AddressWriteRequest.model_validate(
            {"label": "Home", "addressLine1": "Street", "countryCode": 12},
        )


def test_customer_crud_search_filter_and_lifecycle(client: TestClient) -> None:
    beta = _create_customer(client, " beta ", " SALES@Beta.test ")
    alpha = _create_customer(client, "Alpha", "hello@alpha.test")
    alpha_2 = _create_customer(client, "alpha", None)

    assert set(beta) == {
        "id",
        "name",
        "email",
        "status",
        "createdAt",
        "updatedAt",
    }
    assert beta["name"] == "beta"
    assert beta["email"] == "SALES@Beta.test"
    assert beta["status"] == "active"

    listed = client.get("/api/v1/customers")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [
        alpha["id"],
        alpha_2["id"],
        beta["id"],
    ]

    search_by_name = client.get("/api/v1/customers", params={"q": "BET"})
    assert [item["id"] for item in search_by_name.json()] == [beta["id"]]
    search_by_email = client.get("/api/v1/customers", params={"q": "ALPHA.TEST"})
    assert [item["id"] for item in search_by_email.json()] == [alpha["id"]]

    customer_id = int(beta["id"])
    archived = client.put(
        f"/api/v1/customers/{customer_id}",
        json={"name": " Beta Ltd ", "email": " ", "status": "archived"},
    )
    assert archived.status_code == 200
    assert archived.json()["name"] == "Beta Ltd"
    assert archived.json()["email"] is None
    assert archived.json()["status"] == "archived"
    assert archived.json()["updatedAt"] != beta["updatedAt"]

    archived_list = client.get("/api/v1/customers", params={"status": "archived"})
    assert [item["id"] for item in archived_list.json()] == [customer_id]
    assert len(client.get("/api/v1/customers", params={"status": "active"}).json()) == 2

    restored = client.put(
        f"/api/v1/customers/{customer_id}",
        json={"name": "Beta Ltd", "email": None, "status": "active"},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"

    deleted = client.delete(f"/api/v1/customers/{customer_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/customers/{customer_id}").status_code == 404
    remaining_ids = [
        item["id"] for item in client.get("/api/v1/customers").json()
    ]
    assert customer_id not in remaining_ids
    assert client.delete(f"/api/v1/customers/{customer_id}").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "email": None},
        {"name": "Acme", "email": "broken"},
        {"name": 123, "email": None},
        {"name": "Acme", "email": {"invalid": "type"}},
        {"name": "Acme", "email": None, "unexpected": "value"},
    ],
)
def test_customer_create_rejects_invalid_input(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    assert client.post("/api/v1/customers", json=payload).status_code == 422


def test_customer_put_rejects_incomplete_and_deleted_status(client: TestClient) -> None:
    customer = _create_customer(client)
    path = f"/api/v1/customers/{customer['id']}"

    rejected = client.put(path, json={"name": "Acme", "status": "deleted"})
    assert rejected.status_code == 422
    assert client.put(path, json={"name": "Acme"}).status_code == 422


def test_contact_crud_sorting_normalization_and_ownership(client: TestClient) -> None:
    first_customer = _create_customer(client, "First")
    second_customer = _create_customer(client, "Second")
    first_id = int(first_customer["id"])
    second_id = int(second_customer["id"])

    zoe_response = client.post(
        f"/api/v1/customers/{first_id}/contacts",
        json={
            "name": " Zoe ",
            "email": " zoe@example.test ",
            "phone": " ",
            "jobTitle": " CEO ",
        },
    )
    assert zoe_response.status_code == 201
    zoe = zoe_response.json()
    assert zoe["name"] == "Zoe"
    assert zoe["phone"] is None
    assert zoe["jobTitle"] == "CEO"
    assert {"createdAt", "updatedAt"} <= set(zoe)

    amy = client.post(
        f"/api/v1/customers/{first_id}/contacts",
        json={"name": "amy"},
    ).json()
    amy_2 = client.post(
        f"/api/v1/customers/{first_id}/contacts",
        json={"name": "Amy"},
    ).json()
    listed = client.get(f"/api/v1/customers/{first_id}/contacts")
    assert [item["id"] for item in listed.json()] == [amy["id"], amy_2["id"], zoe["id"]]

    cross_path = f"/api/v1/customers/{second_id}/contacts/{zoe['id']}"
    assert client.put(cross_path, json={"name": "Leak"}).status_code == 404
    assert client.delete(cross_path).status_code == 404

    update = client.put(
        f"/api/v1/customers/{first_id}/contacts/{zoe['id']}",
        json={"name": " Zoey ", "email": " ", "phone": " 123 ", "jobTitle": " "},
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Zoey"
    assert update.json()["email"] is None
    assert update.json()["phone"] == "123"

    delete_path = f"/api/v1/customers/{first_id}/contacts/{zoe['id']}"
    assert client.delete(delete_path).status_code == 204
    remaining = client.get(f"/api/v1/customers/{first_id}/contacts").json()
    assert zoe["id"] not in [item["id"] for item in remaining]
    assert client.put(delete_path, json={"name": "Again"}).status_code == 404
    assert client.delete(delete_path).status_code == 404


def test_address_crud_sorting_normalization_and_ownership(client: TestClient) -> None:
    first = _create_customer(client, "First")
    second = _create_customer(client, "Second")
    first_id = int(first["id"])
    second_id = int(second["id"])

    visiting_response = client.post(
        f"/api/v1/customers/{first_id}/addresses",
        json={
            "label": " Visiting ",
            "addressLine1": " Main street 1 ",
            "addressLine2": " ",
            "postalCode": " 00100 ",
            "city": " Helsinki ",
            "region": " ",
            "countryCode": " fi ",
        },
    )
    assert visiting_response.status_code == 201
    visiting = visiting_response.json()
    assert visiting["addressLine1"] == "Main street 1"
    assert visiting["addressLine2"] is None
    assert visiting["countryCode"] == "FI"

    billing = client.post(
        f"/api/v1/customers/{first_id}/addresses",
        json={"label": "billing", "addressLine1": "B 1", "countryCode": "SE"},
    ).json()
    billing_2 = client.post(
        f"/api/v1/customers/{first_id}/addresses",
        json={"label": "Billing", "addressLine1": "B 2", "countryCode": "NO"},
    ).json()
    listed = client.get(f"/api/v1/customers/{first_id}/addresses")
    assert [item["id"] for item in listed.json()] == [
        billing["id"],
        billing_2["id"],
        visiting["id"],
    ]

    cross_path = f"/api/v1/customers/{second_id}/addresses/{visiting['id']}"
    replacement = {"label": "Other", "addressLine1": "Street", "countryCode": "FI"}
    assert client.put(cross_path, json=replacement).status_code == 404
    assert client.delete(cross_path).status_code == 404

    own_path = f"/api/v1/customers/{first_id}/addresses/{visiting['id']}"
    updated = client.put(own_path, json=replacement)
    assert updated.status_code == 200
    assert updated.json()["label"] == "Other"
    assert updated.json()["postalCode"] is None
    assert client.delete(own_path).status_code == 204
    remaining = client.get(f"/api/v1/customers/{first_id}/addresses").json()
    assert visiting["id"] not in [item["id"] for item in remaining]
    assert client.put(own_path, json=replacement).status_code == 404


@pytest.mark.parametrize(
    "path_suffix,payload",
    [
        ("contacts", {"name": " ", "email": None}),
        ("contacts", {"name": "Ada", "email": "invalid"}),
        ("contacts", {"name": "Ada", "phone": 123}),
        ("contacts", {"name": "Ada", "extra": "no"}),
        ("addresses", {"label": " ", "addressLine1": "Street", "countryCode": "FI"}),
        ("addresses", {"label": "Home", "addressLine1": " ", "countryCode": "FI"}),
        ("addresses", {"label": "Home", "addressLine1": "Street", "countryCode": "F1"}),
        ("addresses", {"label": "Home", "addressLine1": "Street", "countryCode": 12}),
        ("addresses", {"label": "Home", "addressLine1": "Street", "countryCode": "ß"}),
    ],
)
def test_nested_create_rejects_invalid_input(
    client: TestClient,
    path_suffix: str,
    payload: dict[str, object],
) -> None:
    customer = _create_customer(client)
    response = client.post(
        f"/api/v1/customers/{customer['id']}/{path_suffix}",
        json=payload,
    )
    assert response.status_code == 422


def test_nested_routes_require_visible_parent(client: TestClient) -> None:
    missing_id = 99999
    assert client.get(f"/api/v1/customers/{missing_id}/contacts").status_code == 404
    assert client.get(f"/api/v1/customers/{missing_id}/addresses").status_code == 404

    customer = _create_customer(client)
    customer_id = int(customer["id"])
    assert client.delete(f"/api/v1/customers/{customer_id}").status_code == 204
    assert client.get(f"/api/v1/customers/{customer_id}/contacts").status_code == 404
    assert client.post(
        f"/api/v1/customers/{customer_id}/addresses",
        json={"label": "Home", "addressLine1": "Street", "countryCode": "FI"},
    ).status_code == 404


def test_customer_delete_soft_deletes_children_with_one_timestamp(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    customer = _create_customer(client)
    customer_id = int(customer["id"])
    contact = client.post(
        f"/api/v1/customers/{customer_id}/contacts",
        json={"name": "Ada"},
    ).json()
    address = client.post(
        f"/api/v1/customers/{customer_id}/addresses",
        json={"label": "Home", "addressLine1": "Street", "countryCode": "FI"},
    ).json()

    assert client.delete(f"/api/v1/customers/{customer_id}").status_code == 204

    with session_factory() as session:
        customer_row = session.get(Customer, customer_id)
        contact_row = session.get(Contact, int(contact["id"]))
        address_row = session.get(CustomerAddress, int(address["id"]))
        assert customer_row is not None
        assert contact_row is not None
        assert address_row is not None
        assert customer_row.status == "deleted"
        assert customer_row.deleted_time is not None
        assert customer_row.deleted_time == contact_row.deleted_time
        assert customer_row.deleted_time == address_row.deleted_time
        assert customer_row.modified_time == customer_row.deleted_time
        assert contact_row.modified_time == contact_row.deleted_time
        assert address_row.modified_time == address_row.deleted_time


def test_customer_delete_rolls_back_when_child_update_fails(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        customer = Customer(name="Acme", status="active")
        session.add(customer)
        session.flush()
        contact = Contact(customer_id=customer.customer_id, name="Ada")
        address = CustomerAddress(
            customer_id=customer.customer_id,
            label="Home",
            address_line_1="Street",
            country_code="FI",
        )
        session.add_all([contact, address])
        session.commit()
        customer_id = customer.customer_id
        contact_id = contact.contact_id
        address_id = address.customer_address_id

        def fail_child_update(
            _mapper: Any,
            _connection: Any,
            _target: CustomerAddress,
        ) -> None:
            raise RuntimeError("simulated database failure")

        event.listen(CustomerAddress, "before_update", fail_child_update)
        try:
            with pytest.raises(RuntimeError, match="simulated database failure"):
                service.delete_customer(session, customer_id, 0)
        finally:
            event.remove(CustomerAddress, "before_update", fail_child_update)

        session.expire_all()
        persisted_customer = session.get(Customer, customer_id)
        persisted_contact = session.get(Contact, contact_id)
        persisted_address = session.get(CustomerAddress, address_id)
        assert persisted_customer is not None
        assert persisted_contact is not None
        assert persisted_address is not None
        assert persisted_customer.status == "active"
        assert persisted_customer.deleted_time is None
        assert persisted_contact.deleted_time is None
        assert persisted_address.deleted_time is None


def test_child_delete_updates_modified_and_deleted_timestamps(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        customer = Customer(name="Acme", status="archived")
        session.add(customer)
        session.flush()
        contact = Contact(customer_id=customer.customer_id, name="Ada")
        address = CustomerAddress(
            customer_id=customer.customer_id,
            label="Home",
            address_line_1="Street",
            country_code="FI",
        )
        session.add_all([contact, address])
        session.commit()

        service.delete_contact(session, customer.customer_id, contact.contact_id, 0)
        service.delete_address(
            session,
            customer.customer_id,
            address.customer_address_id,
            0,
        )
        assert contact.deleted_time is not None
        assert contact.modified_time == contact.deleted_time
        assert address.deleted_time is not None
        assert address.modified_time == address.deleted_time


def test_customer_search_treats_wildcards_as_literal(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    _create_customer(client, "100% Real")
    _create_customer(client, "Ordinary")
    response = client.get("/api/v1/customers", params={"q": "%"})
    assert [item["name"] for item in response.json()] == ["100% Real"]

    with session_factory() as session:
        assert len(session.scalars(select(Customer)).all()) == 2
