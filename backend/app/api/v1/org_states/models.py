from datetime import date as dt_date
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

BigIntPrimaryKey = BigInteger().with_variant(Integer, "sqlite")


class Scenario(Base):
    __tablename__ = "scenarios"

    scenario_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    organisation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("organisations.organisation_id"),
    )
    scenario_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    protected: Mapped[bool] = mapped_column(Boolean, server_default="false")
    source_scenario_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("scenarios.scenario_id"),
        nullable=True,
    )
    initial_state_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("org_states.org_state_id"),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, server_default="1")
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


class OrgState(Base):
    __tablename__ = "org_states"

    org_state_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    scenario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("scenarios.scenario_id", ondelete="CASCADE"),
    )
    org_state_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_date: Mapped[dt_date] = mapped_column(Date, nullable=False)
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


class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    scenario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("scenarios.scenario_id", ondelete="CASCADE"),
    )
    event_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    target_date: Mapped[dt_date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    event_details: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class Timeserie(Base):
    __tablename__ = "timeseries"

    timeserie_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    scenario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("scenarios.scenario_id", ondelete="CASCADE"),
    )
    timeserie_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_unit: Mapped[str] = mapped_column(Text)
    value_unit: Mapped[str] = mapped_column(Text)
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


class TimeserieValue(Base):
    __tablename__ = "timeserie_values"

    timeserie_value_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    timeserie_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("timeseries.timeserie_id", ondelete="CASCADE"),
    )
    date: Mapped[dt_date] = mapped_column(Date)
    value: Mapped[dict[str, object]] = mapped_column(JSON)
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
