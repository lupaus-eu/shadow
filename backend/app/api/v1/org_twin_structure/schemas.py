from datetime import date
from typing import Annotated

from pydantic import Field, field_validator

from app.core.schemas import StrictBaseModel

MIN_POSITION = -100_000.0
MAX_POSITION = 100_000.0

type PositionCoordinate = Annotated[
    float,
    Field(ge=MIN_POSITION, le=MAX_POSITION),
]
type JsonObject = dict[str, object]


class Position(StrictBaseModel):
    x: PositionCoordinate = Field(description="Node x coordinate.")
    y: PositionCoordinate = Field(description="Node y coordinate.")


class PositionUpdate(Position):
    node_id: str = Field(
        min_length=1,
        alias="nodeId",
        description="Stable graph node key.",
    )

    @field_validator("node_id")
    @classmethod
    def node_id_must_not_be_blank(cls, value: str) -> str:
        return _stripped_non_blank(value, "Node id must not be blank.")


class BulkPositionUpdate(StrictBaseModel):
    positions: list[PositionUpdate] = Field(
        min_length=1,
        description="Node positions to update.",
    )


class GraphNodeCreateRequest(StrictBaseModel):
    id: str = Field(min_length=1, description="Stable graph node key.")
    name: str = Field(min_length=1, description="Graph node display name.")
    description: str | None = Field(
        default=None,
        description="Graph node description.",
    )
    node_type_id: str = Field(
        min_length=1,
        alias="nodeTypeId",
        description="Stable node type key.",
    )
    position: Position | None = Field(default=None, description="Node position.")
    attributes: JsonObject = Field(
        default_factory=dict,
        description="Dynamic node attributes.",
    )

    @field_validator("id", "name", "node_type_id")
    @classmethod
    def text_fields_must_not_be_blank(cls, value: str) -> str:
        return _stripped_non_blank(value, "Value must not be blank.")


class GraphNodePatchRequest(StrictBaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        description="Graph node display name.",
    )
    description: str | None = Field(
        default=None,
        description="Graph node description.",
    )
    node_type_id: str | None = Field(
        default=None,
        min_length=1,
        alias="nodeTypeId",
        description="Stable node type key.",
    )
    position: Position | None = Field(default=None, description="Node position.")
    attributes: JsonObject | None = Field(
        default=None,
        description="Dynamic node attributes.",
    )
    timeserie_id: str | None = Field(
        default=None,
        min_length=1,
        alias="timeserieId",
        description="Stable primary timeserie key, or null to clear.",
    )
    timeserie_secondary_id: str | None = Field(
        default=None,
        min_length=1,
        alias="timeserieSecondaryId",
        description="Stable secondary timeserie key, or null to clear.",
    )

    @field_validator("name", "node_type_id", "timeserie_id", "timeserie_secondary_id")
    @classmethod
    def text_fields_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _stripped_non_blank(value, "Value must not be blank.")


class GraphEdgeCreateRequest(StrictBaseModel):
    id: str = Field(min_length=1, description="Stable graph edge key.")
    name: str = Field(min_length=1, description="Graph edge display name.")
    description: str | None = Field(
        default=None,
        description="Graph edge description.",
    )
    edge_type_id: str = Field(
        min_length=1,
        alias="edgeTypeId",
        description="Stable edge type key.",
    )
    source_node_id: str = Field(
        min_length=1,
        alias="sourceNodeId",
        description="Stable source graph node key.",
    )
    target_node_id: str = Field(
        min_length=1,
        alias="targetNodeId",
        description="Stable target graph node key.",
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        description="Dynamic edge attributes.",
    )

    @field_validator("id", "name", "edge_type_id", "source_node_id", "target_node_id")
    @classmethod
    def text_fields_must_not_be_blank(cls, value: str) -> str:
        return _stripped_non_blank(value, "Value must not be blank.")


class GraphEdgePatchRequest(StrictBaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        description="Graph edge display name.",
    )
    description: str | None = Field(
        default=None,
        description="Graph edge description.",
    )
    edge_type_id: str | None = Field(
        default=None,
        min_length=1,
        alias="edgeTypeId",
        description="Stable edge type key.",
    )
    source_node_id: str | None = Field(
        default=None,
        min_length=1,
        alias="sourceNodeId",
        description="Stable source graph node key.",
    )
    target_node_id: str | None = Field(
        default=None,
        min_length=1,
        alias="targetNodeId",
        description="Stable target graph node key.",
    )
    attributes: JsonObject | None = Field(
        default=None,
        description="Dynamic edge attributes.",
    )

    @field_validator("name", "edge_type_id", "source_node_id", "target_node_id")
    @classmethod
    def text_fields_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _stripped_non_blank(value, "Value must not be blank.")


class GraphNodeResponse(StrictBaseModel):
    id: str = Field(description="Stable graph node key.")
    name: str = Field(description="Graph node display name.")
    description: str = Field(description="Graph node description.")
    node_type_id: str = Field(alias="nodeTypeId", description="Stable node type key.")
    create_date: date | None = Field(
        alias="createDate",
        description="Node creation/effective date.",
    )
    delete_date: date | None = Field(
        alias="deleteDate",
        description="Node logical deletion/effective end date.",
    )
    position: Position | None = Field(description="Node position.")
    attributes: JsonObject = Field(description="Dynamic node attributes.")
    timeserie_id: str | None = Field(
        alias="timeserieId",
        description="Stable primary timeserie key linked to this node.",
    )
    timeserie_secondary_id: str | None = Field(
        alias="timeserieSecondaryId",
        description="Stable secondary timeserie key linked to this node.",
    )


class GraphEdgeResponse(StrictBaseModel):
    id: str = Field(description="Stable graph edge key.")
    name: str = Field(description="Graph edge display name.")
    description: str = Field(description="Graph edge description.")
    edge_type_id: str = Field(alias="edgeTypeId", description="Stable edge type key.")
    source_node_id: str = Field(
        alias="sourceNodeId",
        description="Stable source graph node key.",
    )
    target_node_id: str = Field(
        alias="targetNodeId",
        description="Stable target graph node key.",
    )
    create_date: date | None = Field(
        alias="createDate",
        description="Edge creation/effective date.",
    )
    delete_date: date | None = Field(
        alias="deleteDate",
        description="Edge logical deletion/effective end date.",
    )
    attributes: JsonObject = Field(description="Dynamic edge attributes.")


class GraphResponse(StrictBaseModel):
    id: str = Field(description="Stable scenario key for the virtual graph.")
    name: str = Field(description="Scenario display name.")
    description: str = Field(description="Scenario description.")
    nodes: list[GraphNodeResponse] = Field(description="Active graph nodes.")
    edges: list[GraphEdgeResponse] = Field(description="Active graph edges.")


class GraphHistoryResponse(StrictBaseModel):
    nodes: list[GraphNodeResponse] = Field(description="Historical graph nodes.")
    edges: list[GraphEdgeResponse] = Field(description="Historical graph edges.")


class NodeTypeMetadataResponse(StrictBaseModel):
    id: str = Field(description="Stable node type key.")
    name: str | None = Field(description="Node type technical name.")
    display_name: str = Field(
        alias="displayName",
        description="User-friendly node type display name.",
    )
    color: str | None = Field(description="Node UI color.")
    shape: str | None = Field(description="Node UI shape.")
    timeserie_id: str | None = Field(
        alias="timeserieId",
        description="Default primary timeserie key metadata.",
    )
    timeserie_secondary_id: str | None = Field(
        alias="timeserieSecondaryId",
        description="Default secondary timeserie key metadata.",
    )
    timeserie_id_rule: str | None = Field(
        alias="timeserieIdRule",
        description="Timeserie id derivation rule metadata.",
    )


class EdgeTypeMetadataResponse(StrictBaseModel):
    id: str = Field(description="Stable edge type key.")
    name: str | None = Field(description="Edge type technical name.")
    display_name: str = Field(
        alias="displayName",
        description="User-friendly edge type display name.",
    )
    style: str | None = Field(description="Edge UI line style.")
    source_end: str | None = Field(
        alias="sourceEnd",
        description="Edge source ending.",
    )
    target_end: str | None = Field(
        alias="targetEnd",
        description="Edge target ending.",
    )


class AllowedConnectionMetadataResponse(StrictBaseModel):
    edge_type_id: str = Field(
        alias="edgeTypeId",
        description="Stable edge type key allowed for the node type pair.",
    )
    source_node_type_id: str = Field(
        alias="sourceNodeTypeId",
        description="Stable source node type key.",
    )
    target_node_type_id: str = Field(
        alias="targetNodeTypeId",
        description="Stable target node type key.",
    )


class TypeCatalogResponse(StrictBaseModel):
    node_types: list[NodeTypeMetadataResponse] = Field(
        alias="nodeTypes",
        description="Active node type metadata for the active metamodel.",
    )
    edge_types: list[EdgeTypeMetadataResponse] = Field(
        alias="edgeTypes",
        description="Active edge type metadata for the active metamodel.",
    )
    allowed_connections: list[AllowedConnectionMetadataResponse] = Field(
        alias="allowedConnections",
        description="Allowed source/target node type pairs for active edge types.",
    )


class TypeAttributeMetadataResponse(StrictBaseModel):
    owner_kind: str = Field(
        alias="ownerKind",
        description="Owner kind: `node_type` or `edge_type`.",
    )
    owner_type_id: str = Field(
        alias="ownerTypeId",
        description="Stable node or edge type key that owns the attribute.",
    )
    id: str = Field(description="Stable attribute key.")
    name: str | None = Field(description="Attribute technical name.")
    display_name: str = Field(
        alias="displayName",
        description="User-friendly attribute display name.",
    )
    data_type: str = Field(alias="dataType", description="Attribute data type.")
    mandatory: bool = Field(description="Whether the attribute is mandatory.")
    max_length: int | None = Field(
        alias="maxLength",
        description="Maximum text length.",
    )
    multiline: bool | None = Field(description="Whether text may span lines.")


class TypeCatalogWithAttributesResponse(TypeCatalogResponse):
    type_attributes: list[TypeAttributeMetadataResponse] = Field(
        alias="typeAttributes",
        description="Active attribute metadata of the active node and edge types.",
    )


def _stripped_non_blank(value: str, message: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(message)
    return stripped
