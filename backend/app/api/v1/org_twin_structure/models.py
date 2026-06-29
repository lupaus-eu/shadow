from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

BigIntPrimaryKey = BigInteger().with_variant(Integer, "sqlite")


class Metamodel(Base):
    __tablename__ = "metamodels"

    metamodel_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    organisation_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("organisations.organisation_id"),
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


class NodeType(Base):
    __tablename__ = "node_types"

    node_type_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    metamodel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("metamodels.metamodel_id"),
    )
    node_type_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    ui_color: Mapped[str | None] = mapped_column(Text, nullable=True)
    ui_shape: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeserie_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeserie_secondary_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeserie_id_rule: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class EdgeType(Base):
    __tablename__ = "edge_types"

    edge_type_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    metamodel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("metamodels.metamodel_id"),
    )
    edge_type_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    ui_style: Mapped[str | None] = mapped_column(Text, nullable=True)
    ui_source_end: Mapped[str | None] = mapped_column(Text, nullable=True)
    ui_target_end: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class TypeAttribute(Base):
    __tablename__ = "type_attributes"

    type_attribute_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    metamodel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("metamodels.metamodel_id"),
    )
    owner_kind: Mapped[str] = mapped_column(Text)
    owner_node_type_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("node_types.node_type_id"),
        nullable=True,
    )
    owner_edge_type_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("edge_types.edge_type_id"),
        nullable=True,
    )
    attribute_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(Text)
    mandatory: Mapped[bool] = mapped_column(Boolean, server_default="false")
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    multiline: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
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


class AllowedConnection(Base):
    __tablename__ = "allowed_connections"

    allowed_connection_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    metamodel_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("metamodels.metamodel_id"),
    )
    edge_type_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("edge_types.edge_type_id"),
    )
    source_node_type_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("node_types.node_type_id"),
    )
    target_node_type_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("node_types.node_type_id"),
    )
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
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
