from datetime import UTC, datetime
from typing import Any, cast

import pytest
from sqlalchemy import Engine, Table, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.customers.models import Contact, Customer, CustomerAddress
from app.api.v1.users.models import User
from app.core.models import Base


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any,
    _connection_record: Any,
) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture()
def engine() -> Engine:
    sqlite_engine = create_engine("sqlite:///:memory:")
    event.listen(sqlite_engine, "connect", _enable_sqlite_foreign_keys)

    Base.metadata.create_all(
        sqlite_engine,
        tables=[
            cast(Table, User.__table__),
            cast(Table, Customer.__table__),
            cast(Table, Contact.__table__),
            cast(Table, CustomerAddress.__table__),
        ],
    )
    return sqlite_engine


def test_customer_domain_models_persist_valid_records(engine: Engine) -> None:
    with Session(engine) as session:
        customer = Customer(name="Acme", email=None, status="active")
        session.add(customer)
        session.flush()
        session.add_all(
            [
                Contact(customer_id=customer.customer_id, name="Ada"),
                CustomerAddress(
                    customer_id=customer.customer_id,
                    label="Billing",
                    address_line_1="Main street 1",
                    country_code="FI",
                ),
            ],
        )
        session.commit()

        assert customer.customer_id == 1
        assert customer.created_time is not None
        assert customer.modified_time is not None


def test_customer_domain_model_indexes_match_migrations() -> None:
    customer_table = cast(Table, Customer.__table__)
    contact_table = cast(Table, Contact.__table__)
    address_table = cast(Table, CustomerAddress.__table__)

    assert {index.name for index in customer_table.indexes} == {
        "idx_customers_status_name_active",
    }
    assert {index.name for index in contact_table.indexes} == {
        "idx_contacts_customer_name_active",
    }
    assert {index.name for index in address_table.indexes} == {
        "idx_customer_addresses_customer_label_active",
    }


@pytest.mark.parametrize("name", ["", "   ", "\t", "\n", " \t\r\n "])
def test_customer_name_must_not_be_blank(engine: Engine, name: str) -> None:
    with Session(engine) as session:
        session.add(Customer(name=name, status="active"))

        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    ("status", "deleted_time"),
    [
        ("deleted", None),
        ("active", datetime.now(UTC)),
        ("archived", datetime.now(UTC)),
        ("unknown", None),
    ],
)
def test_customer_status_matches_deleted_time(
    engine: Engine,
    status: str,
    deleted_time: datetime | None,
) -> None:
    with Session(engine) as session:
        session.add(
            Customer(
                name="Acme",
                status=status,
                deleted_time=deleted_time,
            ),
        )

        with pytest.raises(IntegrityError):
            session.commit()


def test_deleted_customer_status_with_timestamp_is_valid(engine: Engine) -> None:
    with Session(engine) as session:
        customer = Customer(
            name="Acme",
            status="deleted",
            deleted_time=datetime.now(UTC),
        )
        session.add(customer)
        session.commit()

        assert customer.customer_id == 1


@pytest.mark.parametrize(
    ("label", "address_line_1", "country_code"),
    [
        ("", "Main street 1", "FI"),
        ("\t\n", "Main street 1", "FI"),
        ("Billing", "   ", "FI"),
        ("Billing", "\t\r\n", "FI"),
        ("Billing", "Main street 1", "fin"),
        ("Billing", "Main street 1", "F"),
        ("Billing", "Main street 1", "FIN"),
        ("Billing", "Main street 1", "F1"),
        ("Billing", "Main street 1", "fi"),
        ("Billing", "Main street 1", "ÅA"),
        ("Billing", "Main street 1", "ÄA"),
    ],
)
def test_customer_address_constraints(
    engine: Engine,
    label: str,
    address_line_1: str,
    country_code: str,
) -> None:
    with Session(engine) as session:
        customer = Customer(name="Acme", status="active")
        session.add(customer)
        session.flush()
        session.add(
            CustomerAddress(
                customer_id=customer.customer_id,
                label=label,
                address_line_1=address_line_1,
                country_code=country_code,
            ),
        )

        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize("name", ["", "   ", "\t", "\n", " \t\r\n "])
def test_contact_name_must_not_be_blank(engine: Engine, name: str) -> None:
    with Session(engine) as session:
        customer = Customer(name="Acme", status="active")
        session.add(customer)
        session.flush()
        session.add(Contact(customer_id=customer.customer_id, name=name))

        with pytest.raises(IntegrityError):
            session.commit()


def test_physical_customer_delete_cascades_to_children(engine: Engine) -> None:
    with Session(engine) as session:
        customer = Customer(name="Acme", status="active")
        session.add(customer)
        session.flush()
        session.add(Contact(customer_id=customer.customer_id, name="Ada"))
        session.add(
            CustomerAddress(
                customer_id=customer.customer_id,
                label="Billing",
                address_line_1="Main street 1",
                country_code="FI",
            ),
        )
        session.commit()

        session.delete(customer)
        session.commit()

        assert session.query(Contact).count() == 0
        assert session.query(CustomerAddress).count() == 0
