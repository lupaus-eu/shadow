from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.api.v1.mcp_oauth.models import McpOauthGrant
from app.api.v1.org_states.models import Scenario
from app.api.v1.organisations.models import Organisation
from app.api.v1.users.models import User, non_blank_constraints
from app.core.models import Base

BigIntPrimaryKey = BigInteger().with_variant(Integer, "sqlite")
# Python None is stored as SQL NULL, not as a JSON null.
NullableJSON = JSON(none_as_null=True)

CHANGE_SET_STATUSES = (
    "draft",
    "submitted",
    "applied",
    "rejected",
    "failed",
    "discarded",
)
OPERATION_TYPES = (
    "create_scenario",
    "copy_scenario",
    "create_org_state",
    "create_node",
    "create_edge",
    "patch_node",
    "create_timeserie",
    "set_timeserie_values",
    "generate_timeserie_values",
    "create_derived_metric",
    "create_event",
)
# How a human reviewed a change set: the Metrics tab, or an approved MCP call.
REVIEW_CHANNELS = ("web", "mcp")
# Operations whose created key is server-generated and may be named by a ref.
REF_OPERATION_TYPES = (
    "create_scenario",
    "copy_scenario",
    "create_org_state",
    "create_event",
    "create_derived_metric",
)


def _in_list(column_name: str, values: tuple[str, ...]) -> str:
    return f"{column_name} IN ({', '.join(f"'{value}'" for value in values)})"


class AiChangeSet(Base):
    __tablename__ = "ai_change_sets"
    __table_args__ = (
        UniqueConstraint("change_set_key", name="uq_ai_change_sets_key"),
        *non_blank_constraints("change_set_key", "ck_ai_change_sets_key_non_blank"),
        *non_blank_constraints("title", "ck_ai_change_sets_title_non_blank"),
        *non_blank_constraints("client_id", "ck_ai_change_sets_client_id_non_blank"),
        CheckConstraint(
            "length(client_name) BETWEEN 1 AND 100",
            name="ck_ai_change_sets_client_name_length",
        ),
        CheckConstraint(
            _in_list("status", CHANGE_SET_STATUSES),
            name="ck_ai_change_sets_status",
        ),
        CheckConstraint(
            "(status IN ('applied', 'failed')) = (applied_result IS NOT NULL)",
            name="ck_ai_change_sets_applied_result",
        ),
        CheckConstraint(
            "(reviewed_by IS NULL) = (reviewed_time IS NULL)",
            name="ck_ai_change_sets_review_audit",
        ),
        CheckConstraint(
            "(status IN ('applied', 'rejected', 'failed')) = "
            "(reviewed_time IS NOT NULL)",
            name="ck_ai_change_sets_review_state",
        ),
        CheckConstraint(
            "review_note IS NULL OR reviewed_time IS NOT NULL",
            name="ck_ai_change_sets_review_note",
        ),
        CheckConstraint(
            "(reviewed_via IS NULL) = (reviewed_time IS NULL) AND "
            f"(reviewed_via IS NULL OR {_in_list('reviewed_via', REVIEW_CHANNELS)})",
            name="ck_ai_change_sets_reviewed_via",
        ),
        CheckConstraint(
            "(review_client_id IS NULL) = (review_client_name IS NULL) AND "
            "COALESCE(reviewed_via = 'mcp', false) = (review_client_id IS NOT NULL)",
            name="ck_ai_change_sets_review_client",
        ),
        *non_blank_constraints(
            "review_client_id", "ck_ai_change_sets_review_client_id_non_blank"
        ),
        CheckConstraint(
            "length(review_client_name) BETWEEN 1 AND 100",
            name="ck_ai_change_sets_review_client_name_length",
        ),
    )

    change_set_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    change_set_key: Mapped[str] = mapped_column(Text)
    organisation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(Organisation.organisation_id),
    )
    # Derived from the operations by the engine, never supplied by a client.
    scenario_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(Scenario.scenario_id),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    grant_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(McpOauthGrant.grant_id, ondelete="SET NULL"),
        nullable=True,
    )
    # Copied plain values, not foreign keys, so they outlive the grant and client.
    client_id: Mapped[str] = mapped_column(Text)
    client_name: Mapped[str] = mapped_column(Text)
    validation_result: Mapped[dict[str, Any] | None] = mapped_column(
        NullableJSON,
        nullable=True,
    )
    applied_result: Mapped[dict[str, Any] | None] = mapped_column(
        NullableJSON,
        nullable=True,
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(User.user_id),
        nullable=True,
    )
    reviewed_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # `web` or `mcp`; for `mcp` the reviewing grant's client, copied like
    # client_id and client_name.
    reviewed_via: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_client_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_client_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey(User.user_id))
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    modified_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(User.user_id),
        nullable=True,
    )
    modified_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class AiChangeSetOperation(Base):
    __tablename__ = "ai_change_set_operations"
    __table_args__ = (
        UniqueConstraint(
            "change_set_id",
            "position",
            name="uq_ai_change_set_operations_position",
        ),
        UniqueConstraint(
            "change_set_id",
            "ref",
            name="uq_ai_change_set_operations_ref",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_ai_change_set_operations_position",
        ),
        CheckConstraint(
            _in_list("op_type", OPERATION_TYPES),
            name="ck_ai_change_set_operations_op_type",
        ),
        CheckConstraint(
            f"ref IS NULL OR {_in_list('op_type', REF_OPERATION_TYPES)}",
            name="ck_ai_change_set_operations_ref",
        ),
        CheckConstraint(
            "frozen_values IS NULL OR op_type = 'generate_timeserie_values'",
            name="ck_ai_change_set_operations_frozen_values",
        ),
    )

    change_set_operation_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey,
        primary_key=True,
        autoincrement=True,
    )
    change_set_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ai_change_sets.change_set_id", ondelete="CASCADE"),
    )
    position: Mapped[int] = mapped_column(Integer)
    ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    op_type: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    frozen_values: Mapped[dict[str, Any] | None] = mapped_column(
        NullableJSON, nullable=True
    )
    error: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON, nullable=True)


Index(
    "idx_ai_change_sets_organisation_created",
    AiChangeSet.organisation_id,
    AiChangeSet.created_time.desc(),
    AiChangeSet.change_set_id.desc(),
)
Index(
    "idx_ai_change_sets_scenario_created",
    AiChangeSet.scenario_id,
    AiChangeSet.created_time.desc(),
    AiChangeSet.change_set_id.desc(),
    postgresql_where=AiChangeSet.scenario_id.is_not(None),
    sqlite_where=AiChangeSet.scenario_id.is_not(None),
)
Index(
    "idx_ai_change_sets_grant_id",
    AiChangeSet.grant_id,
    postgresql_where=AiChangeSet.grant_id.is_not(None),
    sqlite_where=AiChangeSet.grant_id.is_not(None),
)
