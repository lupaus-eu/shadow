"""Typed AI change-set operations and engine results (ADR-015).

Operation payloads reuse the owning domains' REST request schemas, so their
JSON keys are REST's camelCase aliases (snake_case names are also accepted).
The addressing fields around a payload (`scenario_key`, `org_state_key`,
`node_key`, `timeserie_key`) are snake_case like the MCP tool arguments.

`$ref` symbols name only server-generated keys: created or copied scenarios,
organisation states, events and derived metrics. Graph nodes, graph edges and
timeseries keep their client-supplied `id`, which later operations repeat
verbatim, so a client-supplied key must not start with `$`.
"""

import re
from datetime import date as dt_date
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, Field, TypeAdapter, model_validator

from app.api.v1.org_states.schemas import (
    DerivedMetricCreateRequest,
    EventCreateRequest,
    OrgStateCreateRequest,
    ScenarioCopyRequest,
    ScenarioCreateRequest,
    TimeserieCreateRequest,
    TimeserieValuesPatchRequest,
)
from app.api.v1.org_twin_structure.schemas import (
    GraphEdgeCreateRequest,
    GraphNodeCreateRequest,
    GraphNodePatchRequest,
)
from app.api.v1.timeserie_generation.schemas import (
    GeneratedPoint,
    TimeserieGenerationSpec,
)
from app.core.schemas import StrictBaseModel

MAX_CHANGE_SET_OPERATIONS = 500
MAX_CHANGE_SET_VALUES = 20_000
MAX_KEY_LENGTH = 128
REF_PATTERN = re.compile(r"\$[A-Za-z][A-Za-z0-9_]{0,63}")

type RefKind = Literal["scenario", "org_state", "event", "derived_metric"]


def _key_or_ref(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Value must not be blank.")
    if stripped.startswith("$") and REF_PATTERN.fullmatch(stripped) is None:
        raise ValueError(
            f"{stripped} is not a valid $ref symbol; use $ followed by a letter "
            "and up to 63 letters, digits or underscores."
        )
    return stripped


def _client_key(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Value must not be blank.")
    if stripped.startswith("$"):
        raise ValueError(
            "Graph node, graph edge and timeserie keys are client-supplied and "
            "must not start with $; refer to them verbatim."
        )
    return stripped


def _ensure_client_keys(**keys: str | None) -> None:
    for name, value in keys.items():
        if value is not None and value.startswith("$"):
            raise ValueError(
                f"{name} {value} must not start with $: graph node, graph edge "
                "and timeserie keys are client-supplied and referred to verbatim."
            )


KeyOrRef = Annotated[
    str,
    Field(min_length=1, max_length=MAX_KEY_LENGTH),
    AfterValidator(_key_or_ref),
]
ClientKey = Annotated[
    str,
    Field(min_length=1, max_length=MAX_KEY_LENGTH),
    AfterValidator(_client_key),
]
RefSymbol = Annotated[
    str,
    Field(
        pattern=r"^\$[A-Za-z][A-Za-z0-9_]{0,63}$",
        description=(
            "Symbol for the key this operation creates, for example $plan. "
            "Later operations use it where that key is needed."
        ),
    ),
]
ScenarioKey = Annotated[
    KeyOrRef,
    Field(
        description="Existing scenario key, or the $ref of a scenario created earlier.",
    ),
]
OrgStateKey = Annotated[
    KeyOrRef,
    Field(
        description=(
            "Existing organisation state key, or the $ref of an organisation "
            "state created earlier in the same scenario."
        ),
    ),
]


class CreateScenarioOperation(StrictBaseModel):
    type: Literal["create_scenario"]
    ref: RefSymbol | None = None
    payload: ScenarioCreateRequest


class CopyScenarioOperation(StrictBaseModel):
    type: Literal["copy_scenario"]
    ref: RefSymbol | None = None
    payload: ScenarioCopyRequest

    @model_validator(mode="after")
    def sources_may_be_refs(self) -> "CopyScenarioOperation":
        _key_or_ref(self.payload.source_scenario_id)
        _key_or_ref(self.payload.source_org_state_id)
        return self


class CreateOrgStateOperation(StrictBaseModel):
    type: Literal["create_org_state"]
    ref: RefSymbol | None = None
    scenario_key: ScenarioKey
    payload: OrgStateCreateRequest


class CreateEventOperation(StrictBaseModel):
    type: Literal["create_event"]
    ref: RefSymbol | None = None
    scenario_key: ScenarioKey
    payload: EventCreateRequest


class CreateTimeserieOperation(StrictBaseModel):
    type: Literal["create_timeserie"]
    scenario_key: ScenarioKey
    payload: TimeserieCreateRequest

    @model_validator(mode="after")
    def timeserie_key_is_client_supplied(self) -> "CreateTimeserieOperation":
        _ensure_client_keys(id=self.payload.id)
        return self


class SetTimeserieValuesOperation(StrictBaseModel):
    type: Literal["set_timeserie_values"]
    scenario_key: ScenarioKey
    timeserie_key: ClientKey
    payload: TimeserieValuesPatchRequest


class GenerateTimeserieValuesOperation(StrictBaseModel):
    type: Literal["generate_timeserie_values"]
    scenario_key: ScenarioKey
    timeserie_key: ClientKey
    spec: TimeserieGenerationSpec


class CreateDerivedMetricOperation(StrictBaseModel):
    type: Literal["create_derived_metric"]
    ref: RefSymbol | None = None
    scenario_key: ScenarioKey
    payload: DerivedMetricCreateRequest


class CreateNodeOperation(StrictBaseModel):
    type: Literal["create_node"]
    scenario_key: ScenarioKey
    org_state_key: OrgStateKey
    payload: GraphNodeCreateRequest

    @model_validator(mode="after")
    def node_key_is_client_supplied(self) -> "CreateNodeOperation":
        _ensure_client_keys(id=self.payload.id)
        return self


class PatchNodeOperation(StrictBaseModel):
    type: Literal["patch_node"]
    scenario_key: ScenarioKey
    org_state_key: OrgStateKey
    node_key: ClientKey
    payload: GraphNodePatchRequest

    @model_validator(mode="after")
    def patches_something(self) -> "PatchNodeOperation":
        if not self.payload.model_fields_set:
            raise ValueError("Provide at least one graph node field to patch.")
        # A derived metric created earlier may be linked through its $ref.
        for value in (self.payload.timeserie_id, self.payload.timeserie_secondary_id):
            if value is not None:
                _key_or_ref(value)
        return self


class CreateEdgeOperation(StrictBaseModel):
    type: Literal["create_edge"]
    scenario_key: ScenarioKey
    org_state_key: OrgStateKey
    payload: GraphEdgeCreateRequest

    @model_validator(mode="after")
    def edge_keys_are_client_supplied(self) -> "CreateEdgeOperation":
        _ensure_client_keys(
            id=self.payload.id,
            sourceNodeId=self.payload.source_node_id,
            targetNodeId=self.payload.target_node_id,
        )
        return self


type ChangeSetOperation = Annotated[
    CreateScenarioOperation
    | CopyScenarioOperation
    | CreateOrgStateOperation
    | CreateNodeOperation
    | CreateEdgeOperation
    | PatchNodeOperation
    | CreateTimeserieOperation
    | SetTimeserieValuesOperation
    | GenerateTimeserieValuesOperation
    | CreateDerivedMetricOperation
    | CreateEventOperation,
    Field(discriminator="type"),
]
OPERATION_ADAPTER: TypeAdapter[ChangeSetOperation] = TypeAdapter(ChangeSetOperation)
REF_KIND_BY_OPERATION_TYPE: dict[str, RefKind] = {
    "create_scenario": "scenario",
    "copy_scenario": "scenario",
    "create_org_state": "org_state",
    "create_event": "event",
    "create_derived_metric": "derived_metric",
}


def operation_value_count(operation: ChangeSetOperation) -> int:
    """Number of timeserie values the operation sets or generates."""
    if isinstance(operation, SetTimeserieValuesOperation):
        return len(operation.payload.values)
    if isinstance(operation, GenerateTimeserieValuesOperation):
        return operation.spec.point_count()
    return 0


class FrozenValues(StrictBaseModel):
    """Generated values frozen on submit together with the generator version."""

    generator_version: int = Field(alias="generatorVersion")
    values: list[GeneratedPoint]


type OperationStatus = Literal["ok", "error", "not_run"]
type OperationErrorCode = Literal[
    "domain_error",
    "invalid_reference",
    "invalid_operation",
    "generation_error",
    "conflict",
    "lock_timeout",
    "statement_timeout",
    "unexpected_error",
]
type ApplyStep = Literal[
    "lock",
    "status",
    "fingerprint",
    "revalidate",
    "execute",
    "commit",
]


class OperationError(StrictBaseModel):
    code: OperationErrorCode
    message: str
    status_code: int | None = None


class OperationResult(StrictBaseModel):
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
    error: OperationError | None = None


class ExecutionResult(StrictBaseModel):
    """Per-operation results in order and the `$ref` to real key map.

    Execution stops at the first failing operation: earlier operations are
    `ok`, the failing one is `error` and later ones are `not_run`.
    """

    ok: bool
    operations: list[OperationResult]
    refs: dict[str, str]


class ApplyOutcome(StrictBaseModel):
    """The stored `applied_result` of an applied or failed change set.

    A failed outcome names the apply step and its error. Its operation
    statuses show how far execution got before everything was rolled back, so
    it carries no created keys.
    """

    status: Literal["applied", "failed"]
    step: ApplyStep | None = None
    error: OperationError | None = None
    operations: list[OperationResult]
    refs: dict[str, str]


class NodeReplacement(StrictBaseModel):
    kind: Literal["node"] = "node"
    scenario_key: str
    org_state_key: str
    node_key: str
    missing: bool = False
    message: str | None = None
    fields: dict[str, Any] | None = Field(
        default=None,
        description="The patched fields with their current values.",
    )
    checksum: str | None = None


class TimeserieReplacement(StrictBaseModel):
    kind: Literal["timeserie"] = "timeserie"
    scenario_key: str
    timeserie_key: str
    missing: bool = False
    message: str | None = None
    value_count: int | None = None
    first_date: dt_date | None = None
    last_date: dt_date | None = None
    checksum: str | None = None


type ReplacementSummary = Annotated[
    NodeReplacement | TimeserieReplacement,
    Field(discriminator="kind"),
]


class OperationReplacement(StrictBaseModel):
    position: int
    op_type: str
    replaces_existing: bool
    summary: ReplacementSummary | None = None


class ReplacementReport(StrictBaseModel):
    operations: list[OperationReplacement]
    review_fingerprint: str


type ChangeSetStatus = Literal[
    "draft", "submitted", "applied", "rejected", "failed", "discarded"
]
# How a human reviewed a change set: in the Metrics tab (`web`) or by
# approving an MCP client's apply or reject call (`mcp`).
type ReviewChannelName = Literal["web", "mcp"]


class ChangeSetSummary(StrictBaseModel):
    """A change set without its operations, as the MCP tools return it."""

    id: str = Field(description="Change set key, the tools' change_set_key.")
    organisation_key: str
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
        description="Name the staging MCP client declared for itself."
    )
    created_by: int = Field(description="User id of the creator.")
    created_time: datetime
    modified_time: datetime
    reviewed_by: int | None = Field(description="User id of the human reviewer.")
    reviewed_time: datetime | None
    review_note: str | None
    reviewed_via: ReviewChannelName | None = Field(
        description="How the human reviewed it: `web` (the Metrics tab) or `mcp` "
        "(an approved MCP client call)."
    )
    review_client_id: str | None = Field(
        description="client_id of the MCP client that applied or rejected it; "
        "null unless reviewed_via is `mcp`."
    )
    review_client_name: str | None = Field(
        description="Name the reviewing MCP client declared for itself; null "
        "unless reviewed_via is `mcp`."
    )


class FrozenValuesSummary(StrictBaseModel):
    generator_version: int
    value_count: int
    first_date: dt_date | None
    last_date: dt_date | None


class ChangeSetOperationDetail(StrictBaseModel):
    position: int = Field(
        description="Position in the change set; remove_operation takes it."
    )
    type: str
    ref: str | None
    operation: dict[str, Any] = Field(
        description="The stored operation JSON, as add_operations accepts it."
    )
    error: OperationError | None = Field(
        description="The operation's error from the latest validation or apply."
    )
    frozen_values: FrozenValuesSummary | None = Field(
        description="Summary of the generated values frozen on submit."
    )


class ChangeSetDetail(ChangeSetSummary):
    operations: list[ChangeSetOperationDetail]
    validation_result: ExecutionResult | None = Field(
        description="Result of the latest validation or submit dry-run; cleared "
        "whenever the operations change. Its server-generated keys are "
        "provisional."
    )
    applied_result: ApplyOutcome | None = Field(
        description="Result of the apply of an applied or failed change set."
    )
