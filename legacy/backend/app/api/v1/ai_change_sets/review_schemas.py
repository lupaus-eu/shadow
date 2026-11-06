"""Cookie-session review API models for AI change sets (ADR-015, TASK-069K).

The JSON keys are camelCase like the rest of `/api/v1`. The engine results
and the MCP tool models in `schemas.py` keep their snake_case names; these
models mirror them for the Metrics tab and are built from them by field name.
The stored operation JSON is returned as it was staged.
"""

from datetime import date as dt_date
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.api.v1.ai_change_sets.schemas import (
    ApplyStep,
    ChangeSetStatus,
    OperationErrorCode,
    OperationStatus,
    ReviewChannelName,
)
from app.api.v1.timeserie_generation.schemas import GeneratedPoint
from app.core.schemas import StrictBaseModel

# Frozen generated values of one operation are returned up to this count;
# beyond it only their summary is returned.
INLINE_FROZEN_VALUES_LIMIT = 1_000
MAX_REVIEW_NOTE_LENGTH = 2_000
LIST_CHANGE_SETS_DEFAULT_LIMIT = 100
LIST_CHANGE_SETS_MAX_LIMIT = 200


class ReviewModel(StrictBaseModel):
    model_config = ConfigDict(alias_generator=to_camel)


class ReviewOperationError(ReviewModel):
    code: OperationErrorCode
    message: str
    status_code: int | None = None


class ReviewOperationResult(ReviewModel):
    position: int
    op_type: str
    status: OperationStatus
    scenario_key: str | None = Field(
        default=None,
        description="Key of the scenario the operation created or changed.",
    )
    key: str | None = Field(
        default=None,
        description="Key of the row the operation created or changed.",
    )
    error: ReviewOperationError | None = None


class ReviewExecutionResult(ReviewModel):
    ok: bool
    operations: list[ReviewOperationResult]
    refs: dict[str, str]


class ReviewApplyOutcome(ReviewModel):
    status: Literal["applied", "failed"]
    step: ApplyStep | None = None
    error: ReviewOperationError | None = None
    operations: list[ReviewOperationResult]
    refs: dict[str, str]


class ReviewNodeReplacement(ReviewModel):
    kind: Literal["node"] = "node"
    scenario_key: str
    org_state_key: str
    node_key: str
    missing: bool = False
    message: str | None = None
    fields: dict[str, Any] | None = Field(
        default=None,
        description="The patched fields, by their request names, with their "
        "current values.",
    )
    checksum: str | None = None


class ReviewTimeserieReplacement(ReviewModel):
    kind: Literal["timeserie"] = "timeserie"
    scenario_key: str
    timeserie_key: str
    missing: bool = False
    message: str | None = None
    value_count: int | None = None
    first_date: dt_date | None = None
    last_date: dt_date | None = None
    checksum: str | None = None


type ReviewReplacement = Annotated[
    ReviewNodeReplacement | ReviewTimeserieReplacement,
    Field(discriminator="kind"),
]


class ReviewFrozenValues(ReviewModel):
    generator_version: int
    value_count: int
    first_date: dt_date | None
    last_date: dt_date | None
    values: list[GeneratedPoint] | None = Field(
        description=f"The frozen values, or null when there are more than "
        f"{INLINE_FROZEN_VALUES_LIMIT}."
    )


class ChangeSetListItem(ReviewModel):
    id: str = Field(description="Change set key.")
    scenario_key: str | None = Field(
        description="Derived scenario reference: the one existing scenario every "
        "operation targets. Null when the change set creates or copies a "
        "scenario, touches several scenarios or has no operations."
    )
    title: str
    rationale: str | None
    status: ChangeSetStatus
    operation_count: int
    client_id: str = Field(description="client_id of the MCP client that staged it.")
    client_name: str = Field(
        description="Name the staging MCP client declared for itself; "
        "self-declared and not verified."
    )
    created_by: int = Field(description="User id of the creator.")
    created_by_name: str
    created_time: datetime
    modified_time: datetime
    reviewed_by: int | None = Field(description="User id of the human reviewer.")
    reviewed_by_name: str | None
    reviewed_time: datetime | None
    review_note: str | None
    reviewed_via: ReviewChannelName | None = Field(
        description="How the human reviewed it: `web` (the Metrics tab) or `mcp` "
        "(an approved MCP client call)."
    )
    review_client_id: str | None = Field(
        description="client_id of the MCP client that applied or rejected it."
    )
    review_client_name: str | None = Field(
        description="Name the reviewing MCP client declared for itself; "
        "self-declared and not verified."
    )


class ChangeSetReviewOperation(ReviewModel):
    position: int
    type: str
    ref: str | None
    operation: dict[str, Any] = Field(
        description="The stored operation JSON, as it was staged."
    )
    error: ReviewOperationError | None = Field(
        description="The operation's error from the latest validation or apply."
    )
    frozen_values: ReviewFrozenValues | None = Field(
        description="Generated values frozen on submit."
    )
    replaces_existing: bool = Field(
        description="Whether the operation replaces data that existed before the "
        "change set, recomputed against current data on every read."
    )
    replaces: ReviewReplacement | None = Field(
        description="Summary of the current data the operation replaces; "
        "`missing` when the target no longer exists."
    )


class ChangeSetReviewDetail(ChangeSetListItem):
    operations: list[ChangeSetReviewOperation]
    review_fingerprint: str = Field(
        description="Hash of the replacement flags, summaries and per-target "
        "checksums. Apply must send it back."
    )
    validation_result: ReviewExecutionResult | None
    applied_result: ReviewApplyOutcome | None


class ChangeSetApplyRequest(ReviewModel):
    review_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ChangeSetRejectRequest(ReviewModel):
    note: str | None = Field(default=None, max_length=MAX_REVIEW_NOTE_LENGTH)

    @field_validator("note")
    @classmethod
    def note_is_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if "\x00" in value:
            raise ValueError("Note must not contain NUL characters.")
        return value.strip() or None


class ChangeSetApplyResponse(ReviewModel):
    change_set: ChangeSetListItem
    operations: list[ReviewOperationResult] = Field(
        description="Per-operation results with the created or changed keys."
    )
    refs: dict[str, str] = Field(description="Each `$ref` symbol's created key.")
