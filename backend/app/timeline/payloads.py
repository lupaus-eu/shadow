"""The shape of each change's payload, validated with Pydantic and stored as JSON."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddNode(_Payload):
    node_type_id: UUID
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    x: float = 0
    y: float = 0


class RemoveNode(_Payload):
    pass


class UpdateNode(_Payload):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    node_type_id: UUID | None = None

    @model_validator(mode="after")
    def _something_changes(self) -> "UpdateNode":
        if not self.model_fields_set & {"name", "description", "node_type_id"}:
            raise ValueError("update_node must change something")
        return self


class AddConnection(_Payload):
    connection_type_id: UUID
    source_node_id: UUID
    target_node_id: UUID


class RemoveConnection(_Payload):
    pass


class RerouteConnection(_Payload):
    source_node_id: UUID | None = None
    target_node_id: UUID | None = None

    @model_validator(mode="after")
    def _something_changes(self) -> "RerouteConnection":
        if self.source_node_id is None and self.target_node_id is None:
            raise ValueError("reroute_connection needs a new source or target")
        return self


class ChangeConnectionType(_Payload):
    connection_type_id: UUID


PAYLOADS: dict[str, type[_Payload]] = {
    "add_node": AddNode,
    "remove_node": RemoveNode,
    "update_node": UpdateNode,
    "add_connection": AddConnection,
    "remove_connection": RemoveConnection,
    "reroute_connection": RerouteConnection,
    "change_connection_type": ChangeConnectionType,
}


def parse_payload(op: str, payload: dict[str, Any]) -> _Payload:
    """Validate a payload for its operation; raises ``ValueError`` (or Pydantic's) on a bad shape."""
    try:
        model = PAYLOADS[op]
    except KeyError as error:
        raise ValueError(f"unknown change operation: {op}") from error
    return model.model_validate(payload)


def dump_payload(op: str, payload: dict[str, Any]) -> dict[str, Any]:
    """The JSON form to store: validated, with unset optional fields left out."""
    return parse_payload(op, payload).model_dump(mode="json", exclude_unset=True)
