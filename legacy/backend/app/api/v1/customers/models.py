from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

BigIntPrimaryKey = BigInteger().with_variant(Integer, "sqlite")


def non_blank_constraints(
    column_name: str,
    constraint_name: str,
) -> tuple[CheckConstraint, CheckConstraint]:
    postgres_constraint = CheckConstraint(
        f"{column_name} ~ '[^[:space:]]'",
        name=constraint_name,
    ).ddl_if(dialect="postgresql")
    sqlite_constraint = CheckConstraint(
        f"length(trim({column_name}, "
        "char(9) || char(10) || char(11) || char(12) || char(13) || ' ')) > 0",
        name=f"{constraint_name}_sqlite",
    ).ddl_if(dialect="sqlite")
    return postgres_constraint, sqlite_constraint


def country_code_constraints() -> tuple[CheckConstraint, CheckConstraint]:
    postgres_constraint = CheckConstraint(
        'country_code COLLATE "C" ~ \'^[A-Z]{2}$\'',
        name="ck_customer_addresses_country_code",
    ).ddl_if(dialect="postgresql")
    sqlite_constraint = CheckConstraint(
        "length(country_code) = 2 "
        "AND unicode(substr(country_code, 1, 1)) BETWEEN 65 AND 90 "
        "AND unicode(substr(country_code, 2, 1)) BETWEEN 65 AND 90",
        name="ck_customer_addresses_country_code_sqlite",
    ).ddl_if(dialect="sqlite")
    return postgres_constraint, sqlite_constraint


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        *non_blank_constraints("name", "ck_customers_name_non_blank"),
        CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="ck_customers_status",
        ),
        CheckConstraint(
            "(status = 'deleted' AND deleted_time IS NOT NULL) "
            "OR (status IN ('active', 'archived') AND deleted_time IS NULL)",
            name="ck_customers_deleted_status",
        ),
    )

    customer_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="active")
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    modified_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    modified_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    deleted_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = non_blank_constraints("name", "ck_contacts_name_non_blank")

    contact_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    modified_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    modified_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    deleted_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class CustomerAddress(Base):
    __tablename__ = "customer_addresses"
    __table_args__ = (
        *non_blank_constraints(
            "label",
            "ck_customer_addresses_label_non_blank",
        ),
        *non_blank_constraints(
            "address_line_1",
            "ck_customer_addresses_address_line_1_non_blank",
        ),
        *country_code_constraints(),
    )

    customer_address_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    customer_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("customers.customer_id", ondelete="CASCADE"),
    )
    label: Mapped[str] = mapped_column(Text)
    address_line_1: Mapped[str] = mapped_column(Text)
    address_line_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    modified_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    modified_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    deleted_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id"),
        nullable=True,
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


Index(
    "idx_customers_status_name_active",
    Customer.status,
    func.lower(Customer.name),
    Customer.customer_id,
    postgresql_where=Customer.deleted_time.is_(None),
    sqlite_where=Customer.deleted_time.is_(None),
)
Index(
    "idx_contacts_customer_name_active",
    Contact.customer_id,
    func.lower(Contact.name),
    Contact.contact_id,
    postgresql_where=Contact.deleted_time.is_(None),
    sqlite_where=Contact.deleted_time.is_(None),
)
Index(
    "idx_customer_addresses_customer_label_active",
    CustomerAddress.customer_id,
    func.lower(CustomerAddress.label),
    CustomerAddress.customer_address_id,
    postgresql_where=CustomerAddress.deleted_time.is_(None),
    sqlite_where=CustomerAddress.deleted_time.is_(None),
)
